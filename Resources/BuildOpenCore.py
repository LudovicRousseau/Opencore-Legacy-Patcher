# Commands for building the EFI and SMBIOS

from __future__ import print_function

import binascii
import json
import os
import plistlib
import shutil
import subprocess
import sys
import uuid
import zipfile
from distutils.dir_util import copy_tree
from pathlib import Path

from Resources import ModelArray, Versions, utilities
import re

# Find SMBIOS of machine
current_model = subprocess.Popen("system_profiler SPHardwareDataType".split(), stdout=subprocess.PIPE)
current_model = [line.strip().split(": ", 1)[1] for line in current_model.stdout.read().split("\n") if line.strip().startswith("Model Identifier")][0]


class BuildOpenCore():
    def __init__(self, model):
        self.model = model
        self.config = None

    def build_efi(self):
        if not Path(Versions.build_path).exists():
            Path(Versions.build_path).mkdir()
            print("Created build folder")
        else:
            print("Build folder already present, skipping")

        if Path(Versions.opencore_path_build).exists():
            print("Deleting old copy of OpenCore zip")
            Path(Versions.opencore_path_build).unlink()
        if Path(Versions.opencore_path_done).exists():
            print("Deleting old copy of OpenCore folder")
            shutil.rmtree(Versions.opencore_path_done)
        print()
        print("- Adding OpenCore v" + Versions.opencore_version)
        shutil.copy(Versions.opencore_path, Versions.build_path)
        zipfile.ZipFile(Versions.opencore_path_build).extractall(Versions.build_path)

        print("- Adding config.plist for OpenCore")
        # Setup config.plist for editing
        shutil.copy(Versions.plist_path, Versions.plist_path_build)
        self.config = plistlib.load(Path(Versions.plist_path_build_full).open("rb"))

        for name, version, path in [("Lilu", Versions.airportbcrmfixup_version, Versions.lilu_path), ("WhateverGreen", Versions.whatevergreen_version, Versions.whatevergreen_path)]:
            self.enable_kext(name, version, path)

        for name, version, path, check in [
            # CPU patches
            ("AppleMCEReporterDisabler.kext", Versions.mce_version, Versions.mce_path, lambda: self.model in ModelArray.DualSocket),
            ("AAAMouSSE.kext", Versions.mousse_version, Versions.mousse_path, lambda: self.model in ModelArray.SSEEmulator),
            ("telemetrap.kext", Versions.telemetrap_version, Versions.telemetrap_path, lambda: self.model in ModelArray.MissingSSE42),
            # Ethernet patches
            ("nForceEthernet.kext", Versions.nforce_version, Versions.nforce_path, lambda: self.model in ModelArray.EthernetNvidia),
            ("MarvelYukonEthernet.kext", Versions.marvel_version, Versions.marvel_path, lambda: self.model in ModelArray.EthernetMarvell),
            ("CatalinaBCM5701Ethernet.kext", Versions.bcm570_version, Versions.bcm570_path, lambda: self.model in ModelArray.EthernetBroadcom),
        ]:
            self.enable_kext(name, version, path, check)

        # WiFi patches

        if self.model in ModelArray.WifiAtheros:
            self.enable_kext("IO80211HighSierra", Versions.io80211high_sierra_version, Versions.io80211high_sierra_path)
            self.get_kext_by_bundle_path("IO80211HighSierra.kext/Contents/PlugIns/AirPortAtheros40.kext")["Enabled"] = True

        if self.model in ModelArray.WifiBCM94331:
            self.enable_kext("AirportBrcmFixup", Versions.airportbcrmfixup_version, Versions.airportbcrmfixup_path)
            self.get_kext_by_bundle_path("AirportBrcmFixup.kext/Contents/PlugIns/AirPortBrcmNIC_Injector.kext")["Enabled"] = True

            if current_model in ModelArray.EthernetNvidia:
                # Nvidia chipsets all have the same path to ARPT
                property_path = "PciRoot(0x0)/Pci(0x15,0x0)/Pci(0x0,0x0)"
            if current_model in ("MacBookAir2,1", "MacBookAir3,1", "MacBookAir3,2"):
                property_path = "PciRoot(0x0)/Pci(0x15,0x0)/Pci(0x0,0x0)"
            elif current_model in ("iMac7,1", "iMac8,1"):
                property_path = "PciRoot(0x0)/Pci(0x1C,0x4)/Pci(0x0,0x0)"
            elif current_model in ("iMac13,1", "iMac13,2"):
                property_path = "PciRoot(0x0)/Pci(0x1C,0x3)/Pci(0x0,0x0)"
            elif current_model in ("MacPro5,1"):
                property_path = "PciRoot(0x0)/Pci(0x1C,0x5)/Pci(0x0,0x0)"
            else:
                # Assumes we have a laptop with Intel chipset
                property_path = "PciRoot(0x0)/Pci(0x1C,0x1)/Pci(0x0,0x0)"
            print("- Applying fake ID for WiFi")
            self.config["DeviceProperties"]["Add"][property_path] = {
                "device-id": binascii.unhexlify("ba430000"),
                "compatible": "pci14e4,43ba"
            }

        # HID patches
        if self.model in ModelArray.LegacyHID:
            print("- Adding IOHIDFamily patch")
            self.get_item_by_kv(self.config["Kernel"]["Patch"], "Identifier", "com.apple.iokit.IOHIDFamily")["Enabled"] = True

        map_name = f"USB-Map-{current_model}.zip"
        usb_map_path = Path(Versions.current_path) / Path(f"payloads/Kexts/Maps/Zip/{map_name}")
        if usb_map_path.exists():
            print("- Adding USB Map")
            shutil.copy(usb_map_path, Versions.kext_path_build)
            self.get_kext_by_bundle_path("USB-Map-SMBIOS.kext")["BundlePath"] = map_name

        # Add OpenCanopy
        print("- Adding OpenCanopy GUI")
        shutil.rmtree(Versions.gui_path_build)
        shutil.copy(Versions.gui_path, Versions.plist_path_build)
        self.config["UEFI"]["Drivers"] = ["OpenCanopy.efi", "OpenRuntime.efi"]

    def set_smbios(self):
        spoofed_model = self.model
        if self.model in ModelArray.MacBookAir61:
            print("- Spoofing to MacBookAir6,1")
            spoofed_model = "MacBookAir6,1"
        elif self.model in ModelArray.MacBookAir62:
            print("- Spoofing to MacBookAir6,2")
            spoofed_model = "MacBookAir6,2"
        elif self.model in ModelArray.MacBookPro111:
            print("- Spoofing to MacBookPro11,1")
            spoofed_model = "MacBookPro11,1"
        elif self.model in ModelArray.MacBookPro112:
            print("- Spoofing to MacBookPro11,2")
            spoofed_model = "MacBookPro11,2"
        elif self.model in ModelArray.Macmini71:
            print("- Spoofing to Macmini7,1")
            spoofed_model = "Macmini7,1"
        elif self.model in ModelArray.iMac151:
            print("- Spoofing to iMac15,1")
            spoofed_model = "iMac15,1"
        elif self.model in ModelArray.iMac144:
            print("- Spoofing to iMac14,4")
            spoofed_model = "iMac14,4"
        elif self.model in ModelArray.MacPro71:
            print("- Spoofing to MacPro7,1")
            spoofed_model = "MacPro7,1"
        macserial_output = subprocess.run((f"./payloads/tools/macserial -g -m {spoofed_model} -n 1").split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        macserial_output = macserial_output.stdout.strip().split(" | ")
        self.config["PlatformInfo"]["Generic"]["SystemProductName"] = spoofed_model
        self.config["PlatformInfo"]["Generic"]["SystemSerialNumber"] = macserial_output[0]
        self.config["PlatformInfo"]["Generic"]["MLB"] = macserial_output[1]
        self.config["PlatformInfo"]["Generic"]["SystemUUID"] = str(uuid.uuid4()).upper()

    @staticmethod
    def get_item_by_kv(iterable, key, value):
        item = None
        for i in iterable:
            if i[key] == value:
                item = i
                break
        return item

    def get_kext_by_bundle_path(self, bundle_path):
        kext = self.get_item_by_kv(self.config["Kernel"]["Add"], "BundlePath", bundle_path)
        if not kext:
            print(f"- Could not find kext {bundle_path}!")
            raise IndexError
        return kext

    def enable_kext(self, kext_name, kext_version, kext_path, check=False):
        kext = self.get_kext_by_bundle_path(kext_name)

        if callable(check) and not check():
            # Check failed
            return

        print(f"- Adding {kext_name} {kext_version}")
        shutil.copy(kext_path, Versions.kext_path_build)
        kext["Enabled"] = True

    def cleanup(self):
        print("- Cleaning up files")
        for kext in Path(Versions.kext_path_build).glob("*.zip"):
            with zipfile.ZipFile(kext) as zip_file:
                zip_file.extractall(Versions.kext_path_build)
            kext.unlink()
        shutil.rmtree((Path(Versions.kext_path_build) / Path("__MACOSX")), ignore_errors=True)

        for item in Path(Versions.plist_path_build).glob("*.zip"):
            with zipfile.ZipFile(item) as zip_file:
                zip_file.extractall(Versions.plist_path_build)
            item.unlink()
        shutil.rmtree((Path(Versions.build_path) / Path("__MACOSX")), ignore_errors=True)
        Path(Versions.opencore_path_build).unlink()

    def copy_efi(self):
        diskutil = subprocess.run("diskutil list".split(), stdout=subprocess.PIPE).stdout.decode().strip()
        menu = utilities.TUIMenu(["Select Disk"], "Please select the disk you want to install OpenCore to(ie. disk1): ", in_between=diskutil, return_number_instead_of_direct_call=True, add_quit=False)
        for disk in [i for i in Path("/dev").iterdir() if re.fullmatch("disk[0-9]+", i.stem)]:
            menu.add_menu_option(disk.stem, key=disk.stem[4:])
        disk_num = menu.start()
        print(subprocess.run("sudo diskutil mount disk" + disk_num, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout)

        utilities.cls()
        utilities.header(["Copying OpenCore"])
        efi_dir = Path("/Volumes/EFI")
        if efi_dir.exists():
            print("- Coping OpenCore onto EFI partition")
            if (efi_dir / Path("EFI")).exists():
                print("Removing preexisting EFI folder")
                shutil.rmtree(efi_dir / Path("EFI"))
            if Path(Versions.opencore_path_done).exists():
                shutil.copytree(Versions.opencore_path_done, efi_dir)
                shutil.copy(Versions.icon_path, efi_dir)
                print("OpenCore transfer complete")
                print("")
        else:
            print("Couldn't find EFI partition")
            print("Please ensure your drive is formatted as GUID Partition Table")
            print("")

def MountOpenCore():
    subprocess.Popen((r"sudo diskutil mount $(nvram 4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102:boot-path | sed 's/.*GPT,\([^,]*\),.*/\1/')").split())
