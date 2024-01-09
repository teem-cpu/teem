# TEEM - A CPU Emulator with Transient Execution

## System requirements and installation

The following things need to be installed to run TEEM:

- Python >= 3.8
- Python-Benedict
- Python-Prompt-Toolkit

To install the required packages, one may use the following command:

```
pip install -r requirements.txt
```

## Running the program

The syntax for running TEEM from the root folder of the repository is:

```
./main.py <path_to_target_program>
```

On Windows systems, the following command should be used instead:

```
python main.py <path_to_target_program>
```

There are demo programs available in the `demo` folder, including sample attacks using meltdown and spectre.

The syntax of programs accepted by the emulator is described in [doc/assembly.md](doc/assembly.md) and [doc/isa.md](doc/isa.md).

## Configuration

Edit `config.yml` to change the default settings.

## Compiling C code

TEEM is able to run RISC-V assembly compiled from C code.

For successful compilation you need [`clang 17+`](https://releases.llvm.org/download.html) and can utilize the [`Makefile`](demo/Makefile) in the `demo` directory.

## Copyright & License

Copyright (C) 2022 Felix Betke, Lennart Hein, Melina Hoffmann, Jan-Niklas Sohn

Copyright (C) 2023 Maxim Shevchishin

SPDX-License-Identifier: GPL-2.0-or-later

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You may obtain a copy of the License in the `LICENSE.txt` file, or at: <https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt>

