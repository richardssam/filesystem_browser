./makepackage.csh
/Applications/OpenRV.app/Contents/MacOS/rvpkg -force -remove "Filesystem Browser"
/Applications/OpenRV.app/Contents/MacOS/rvpkg -force -add "/Users/sam/Library/Application Support/RV" filesystembrowser.zip
/Applications/OpenRV.app/Contents/MacOS/rvpkg -force -install "Filesystem Browser"
