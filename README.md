Intel Instruction Set Reference for Dash
========================================

![](https://dl.dropboxusercontent.com/u/37804131/github/Screen%20Shot%202015-03-13%20at%2010.16.35%20AM.png)

This script builds the Dash docset of IA-32/Intel 64 instruction set from Intel 
Instruction Set Reference, which can be downloaded at
http://www.intel.com/content/www/us/en/processors/architectures-software-developer-manuals.html.
Conversion is done by extracting the page number of each instruction, and then rendering
corresponding pages to PNG.

The docset created by this script can be used with [Dash for Mac](http://kapeli.com/dash), 
[Dash for iOS](http://kapeli.com/dash_ios), [Velocity](http://velocity.silverlakesoftware.com/) (for Windows),
and [Zeal](http://zealdocs.org/) (for Linux, Windows).


Requirements
------------

* Python 3.4 (not tested on 2.7, but it might work)
* PyPDF2 1.24
* Pillow
* GhostScript
