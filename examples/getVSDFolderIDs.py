#!/usr/bin/python

from vsdConnect import connectVSD
import sys
import argparse

parser = argparse.ArgumentParser(description='Download original image files from SMIR to a specific folder.')


args=parser.parse_args()
#con=connectVSD.VSDConnecter("username","password")
#con=connectVSD.VSDConnecter()
con=connectVSD.VSDConnecter("ZGVtb0B2aXJ0dWFsc2tlbGV0b24uY2g6ZGVtbw==")
con.seturl("https://demo.virtualskeleton.ch/api/")

print "Retrieving folder list from SMIR.."
folderList=con.getFolderList()


folderHash=con.readFolders(folderList)

for folderKey in folderHash:
    folder=folderHash[folderKey]
    print folder.name, folder.ID, folder.parentFolder


#con.downloadFile(56738)
