#!/usr/bin/python

import connectVSD
import importlib
import sys
import argparse
import logging
import requests
from pathlib import Path
import glob
import time
import dicom  #pip install pydicom

parser = argparse.ArgumentParser(description='Upload series of files to the SMIR to a specific folder')
group = parser.add_mutually_exclusive_group()
group.add_argument('--targetFolderID', dest='targetFolder', default=None, required=0, type = int,
                   help='ID of folder to store images in')
group.add_argument('--targetFolderName', dest='targetFolderName', default=None, required=0,
                   help='Name of folder to store images in')
parser.add_argument('--noglob', action='store_true',
                    help='doesn''t perform pathname expansion')
parser.add_argument('--file', dest='filename', default=[], nargs = '*' ,required=1,
                   help='filenames to upload. can be used with pathname expansion:  --file  myfolder/*.dcm' )
parser.add_argument('--retry', dest='retry', default=3, nargs = '*' ,required=0, type = int,
                   help='Number of upload attempts in case of error' )
parser.add_argument('--loglevel', default='WARNING', help='Log level [CRITICAL, ERROR, WARNING, INFO, DEBUG] default is warning')

# parser.add_argument('--retryTimeout', dest= 'retryTimeout', default=1, required=0, type = int,
#                    help='Timeout in seconds between successive upload attempts')


args=parser.parse_args()
logger = logging.getLogger()
logger.setLevel(args.loglevel)

login_args = dict(
            url='https://demo.virtualskeleton.ch/api/',
            username="demo@virtualskeleton.ch",
            password="demo")


con=connectVSD.VSDConnecter(**login_args)
filenames = []
if args.noglob:
    filenames = [Path(f) for f in args.filename]
else:
    for f in args.filename:
        filenames += [Path(i) for i in glob.glob(f)]
nfiles = float(len(filenames))
print("Uploading %d files" %(nfiles))
uploadedObjects= {}
filesInError = []

for i,f in enumerate(filenames):
    res = None
    uploadAttempts = 0
    while(res is None or isinstance(res,int )) and uploadAttempts <= args.retry:
        if not res in [401] : #if not authorized access will be blocked
            logging.info("%2.0f%% Uploading file %s [%s]" %(i/nfiles*100,f, uploadAttempts))
            res = con.uploadFile(f)
            time.sleep(0.01)
            uploadAttempts += 1
            if isinstance(res,int):
                logging.info(requests.status_codes._codes[res][0])
    try:
        fileUrl = res.selfUrl
        fileAPIObject = con.getFile(fileUrl)
        lastFileObject = fileAPIObject.objects[-1]['selfUrl']
        uploadedObjects[lastFileObject] =  uploadedObjects.get(lastFileObject,[])  +[(fileUrl,f )] #[(fileUrl,fileLcoalPath),(fileUrl,fileLocalPath)]
    except:
        filesInError.append(f)
        if isinstance(res, int):
            status_description = requests.status_codes._codes[res][0]
            logging.error('Upload of file %s not successful. %s %s ' %(f, res, status_description ) )
        else:
            logging.error('Upload of file %s not successful.' %f, exc_info = True)


filesActuallyUploaded = 0
#print("\tObject\t#files\tFileName\tPatient\t\tRows\t\Columns")
for obj in uploadedObjects:
    firstFileUrl=uploadedObjects[obj][0][0]
    firstFileLocalPath=uploadedObjects[obj][0][1]
    datainfo = ' '
    try:
        img = dicom.read_file(firstFileLocalPath.as_posix())
        for tag in ['PatientName','PatientID', 'Rows', 'Colums']:
            datainfo += "%s\t" % (img.get(tag,default=' '))
    except:
        raise

    print("%s \t: %d files \t%s\t%s" %(obj, len(uploadedObjects[obj]),firstFileLocalPath, datainfo ))
    filesActuallyUploaded +=1
print("Uploaded %d files in %d objects" %(len(filenames), filesActuallyUploaded) )

folder = None
if args.targetFolderName:
    folder = con.getFolderByName(args.targetFolderName)[0]
    if not isinstance(folder,connectVSD.APIFolder):
        logging.error('Folder %s not retrieved %s' %(args.targetFolderName, folder))
elif args.targetFolder:
    folder = con.getFolder(args.targetFolder)
    if not isinstance(folder,connectVSD.APIFolder):
        logging.error('Folder %s not retrieved %s' %(args.targetFolder, folder))

if isinstance(folder,connectVSD.APIFolder):
    for obj in uploadedObjects:
        print("Copying object %s to target folder %s " %(obj, folder.name))
        objID= con.getObject(obj)
        con.addObjectToFolder(folder, objID)

sys.exit()
