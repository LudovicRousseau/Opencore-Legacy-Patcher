#!/usr/bin/env python3

from __future__ import print_function

import subprocess
from pathlib import Path

from Resources import build, ModelArray, Versions, utilities

PATCHER_VERSION = "0.0.5"


class OpenCoreLegacyPatcher():
    def __init__(self):
        self.custom_model: str = None
        self.current_model: str = None
        opencore_model: str = subprocess.run("nvram 4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102:oem-product".split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode()
        if not opencore_model.startswith("NVRAM: Error getting variable"):
            opencore_model = subprocess.run("nvram 4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102:oem-product".split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            opencore_model = [line.strip().split(":oem-product	", 1)[1] for line in opencore_model.stdout.decode().split("\n") if line.strip().startswith("4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102:")][0]
            self.current_model = opencore_model
        else:
            self.current_model = subprocess.run("system_profiler SPHardwareDataType".split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.current_model = [line.strip().split(": ", 1)[1] for line in self.current_model.stdout.decode().split("\n") if line.strip().startswith("Model Identifier")][0]

    def build_opencore(self):
        build.OpenCoreMenus().build_opencore_menu(self.custom_model or self.current_model)

    def install_opencore(self):
        utilities.cls()
        utilities.header(["Installing OpenCore to Drive"])

        if Path(Versions.opencore_path_done).exists():
            print("\nFound OpenCore in Build Folder")
            build.BuildOpenCore.copy_efi()
            input("Press enter go back")

        else:
            utilities.TUIOnlyPrint(["Installing OpenCore to Drive"],
                                   "Press enter to go back\n",
                                   ["""OpenCore folder missing!
Please build OpenCore first!"""]).start()

    def change_model(self):
        utilities.cls()
        utilities.header(["Enter New SMBIOS"])
        print("""
Tip: Run the following command on the target machine to find the SMBIOS:

system_profiler SPHardwareDataType | grep 'Model Identifier'
    """)
        self.custom_model = input("Please enter the SMBIOS of the target machine: ").strip()

    def credits(self):
        utilities.TUIOnlyPrint(["Credits"], "Press enter to go back\n",
                               ["""Many thanks to the following:

  - Acidanthera:\tOpenCore, kexts and other tools
  - DhinakG:\t\tWriting and maintaining this patcher
  - Khronokernel:\tWriting and maintaining this patcher
  - Syncretic:\t\tAAAMouSSE and telemetrap
  - Slice:\t\tVoodooHDA"""]).start()

    def main_menu(self):
        response = None
        while not (response and response == -1):
            title = [
                "OpenCore Legacy Patcher v" + PATCHER_VERSION,
                "Selected Model: " + (self.custom_model or self.current_model)
            ]

            if (self.custom_model or self.current_model) not in ModelArray.SupportedSMBIOS:
                in_between = [
                    'Your model is not supported by this patcher!',
                    '',
                    'If you plan to create the USB for another machine, please select option 3'
                ]
            elif not self.custom_model and self.current_model in ("MacPro3,1", "iMac7,1") and \
                    "SSE4.1" not in subprocess.run("sysctl machdep.cpu.features".split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode():
                in_between = [
                    'Your model requires a CPU upgrade to a CPU supporting SSE4.1+ to be supported by this patcher!',
                    '',
                    'If you plan to create the USB for another machine, please select option 5'
                ]
            elif self.custom_model in ("MacPro3,1", "iMac7,1"):
                in_between = ["This model is supported",
                              "However please ensure the CPU has been upgraded to support SSE4.1+"
                              ]
            else:
                in_between = ["This model is supported"]

            menu = utilities.TUIMenu(title, "Choose your fighter: ", in_between=in_between, auto_number=True, top_level=True)

            options = ([["Build OpenCore", self.build_opencore]] if ((self.custom_model or self.current_model) in ModelArray.SupportedSMBIOS) else []) + [
                ["Install OpenCore to USB/internal drive", self.install_opencore],
                ["Change Model", self.change_model],
                ["Credits", self.credits]
            ]

            for option in options:
                menu.add_menu_option(option[0], function=option[1])

            response = menu.start()
            # response = utilities.menu(title, "zoomer, choose your fighter: ", options, auto_number=True, top_level=True)

        print("Bye")


OpenCoreLegacyPatcher().main_menu()
