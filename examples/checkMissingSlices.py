import connectVSD
import logging
import sys
import getpass
import requests
import time

def main():

    c = connectVSD.VSDConnecter()
    object_ids = [121, 73960]
    for id in object_ids:
        try:
            originalFilenames = GetOriginalFilenames(id,c)
            print('id %d has %d files' %(id, len(originalFilenames)))
            if originalFilenames:
                print(id, GetMissingFiles(originalFilenames) )
        except:
            logging.error('exception for id %s' %id, exc_info=True)


def GetOriginalFilenames(id,connection, attempts=1):
    id_info = connection.getObject(id)
    print(id,id_info)
    while (id_info is None) and (attempts > 0):
        #time.sleep(5)
        attempts += -1
        id_info = connection.getObject(id)

    originalFileNames = []
    try:
        print('Object %s, found %d files' %(id, len(id_info.files)))

        for f in id_info.files:
            fileURL = f['selfUrl']
            file_info = connection.getRequest(fileURL)
            originalFileNames.append(file_info['originalFileName'])

    except:
        logging.error('Error in retrieving filenames for id %s' %id, exc_info = False)
    return originalFileNames

def GetMissingFiles(originalFileNames, filenametemplate=None, firstSlice=0, nFiles=-1, suffix = '.dcm'):

    if filenametemplate is None:
            firstfile = originalFileNames[0]
            if firstfile[-len(suffix):].lower() == suffix.lower():
                firstfileBase = firstfile[:-len(suffix)]
                ndigits=0
                for char in firstfileBase[::-1]: #check characters backwards
                    if char.isdigit():
                        ndigits +=1
                    else:
                        break #I am interested only in consecutive digits
            else:
                raise Exception('Filename extension not recognized %s' %firstfile)
            prefix = firstfileBase[:-ndigits]
            filenametemplate = prefix + "%0{}d".format(ndigits) + suffix # "slice%05d.dcm"
            logging.info(filenametemplate)

    missingFiles = []
    i = firstSlice
    while len(originalFileNames)>0 or (i-firstSlice < nFiles)  :
        try:
            curFile = filenametemplate %i
            #print("Checking slice %d / %d" % (i-firstSlice, nFiles))
            originalFileNames.remove(curFile)
        except:
            missingFiles.append(curFile)
        i += 1
    logging.debug(missingFiles)
    return missingFiles

if __name__ == "__main__":
    main()