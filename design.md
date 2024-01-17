# CherryPicker
CherryPicker for image enhancement papers. Made by Hylz.

## Input description
The input is a list of folders. Each folder contains the outputs of a compared method. For example:

["/home/REFID/", "/home/GEM/", "/home/GT/"]

Each method contains a set of images with the same names. For example, there is:

["/home/REFID/000000.png", "/home/REFID/000001.png", ... ]
["/home/GT/000000.png", "/home/GT/000001.png", ... ]

The purpose is to boost the cherrypicking process. The user can quickly compare the results of different methods, and select small patches of images to be highlighted. The highlighted images will be copied to a new folder, which can be used for the PPT generation script.