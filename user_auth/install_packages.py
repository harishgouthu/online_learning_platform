import os

with open("install_packages.txt") as f:
    for line in f:
        line = line.strip()
        if line:
            os.system(line)
