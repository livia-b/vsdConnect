#!/usr/bin/python

import connectVSD
import os
import hashlib
import fnmatch
import requests
from collections import Counter
from pathlib import Path, PurePath, WindowsPath


import logging
logger = logging.getLogger(__name__)


def localFileHash(fp):
    #see VSDConnecter.checkFileInObject
    BLOCKSIZE = 65536
    hasher = hashlib.sha1()

    with open(str(fp),'rb') as afile: #will work for fp as a string or PATH
        buf = afile.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(BLOCKSIZE)
    return hasher.hexdigest()


def iterateFolderContent(baseFolder, filterPattern = None,
                excludePattern = ".*",
                recursive = True):

    for root, dirs, files in os.walk(baseFolder):
        if not recursive:
            dirs = [] #valid only if os.walk in topdown
        if filterPattern:
            files = fnmatch.filter(files, filterPattern)
        for curFile in files:
            if not fnmatch.fnmatch(curFile, excludePattern):
                yield os.path.join(root, curFile)

def fileExtension(file):
    extension = file.lower().rsplit('.',1)[1:]
    if len(extension)==0:
        return ''
    else:
        return extension[0]


def filterImageFiles(files, matchExtensions = ['', 'mha', 'nii', 'mhd', 'nrrd', 'vtk', 'nhdr', 'dcm']):
    matchExtensions = [i.lower() for i in matchExtensions]
    for f in files:
        if fileExtension(f) in matchExtensions:
            yield f

def compareHashDictPair(dict1, generator2,
                               matchOnlyFirstHash=False,
                               matchNumberFiles = False):
    #compaison not symmetric
    dict1 = dict(dict1) #I make a copy because I will pop elements
    if isinstance(generator2, dict):
        generator2 = generator2.iteritems()

    matchingFolders = Counter()
    filesNotIn1 = []
    nFiles1 = len(dict1)
    nFiles2 = 0

    for localHash, curFile in generator2():
        nFiles2 += 1
        foundFile = dict1.pop(localHash.upper(), False)
        if foundFile:
            matchingFolders.update([os.path.dirname(curFile)])
            if matchOnlyFirstHash:
                if matchNumberFiles:
                    nFiles2 += len(generator2)
            break
        else:
            filesNotIn1.append(curFile)

    filesNotIn2 = dict1.values()

    found = True
    if matchNumberFiles:
        found = found and nFiles1 == nFiles2
    if matchOnlyFirstHash:
        found = found and len(matchingFolders) >1
    else:
        found = found and len(filesNotIn2) == 0
    return found == 0, matchingFolders, filesNotIn2, filesNotIn1


class createReport(connectVSD.VSDConnecter):
    _blowOnError = True

    def _httpResponseCheck(self, response):
        """
        check the response of a request call to the resouce.
        """

        try:
            response.raise_for_status()
            return True, response.status_code

        except requests.exceptions.HTTPError as e:
            print("And you get an HTTPError: {0}".format(e))
            if self._blowOnError:
                raise
            return False, response.status_code

    def getAllPaginated(self, resource, rpp=25):
        #generator, should be easier on ram
        res = self.getRequest(resource, rpp=rpp)
        if res:
            page = connectVSD.APIPagination()
            page.set(obj = res)
            for item in page.items:
                yield item
            if page.nextPageUrl:
                for x in self.getAllPaginated(page.nextPageUrl, rpp=rpp):
                    yield x


    def checkLocalFolder_vs_ID(self,folder, objIDList,
                               matchOnlyFirstHash=False,
                               matchNumberFiles = False,
                               filterPattern = None,
                               excludePattern = ".*",
                               recursive = True):



        localFiles = iterateFolderContent(folder,
                                            filterPattern=filterPattern, excludePattern=excludePattern, recursive=recursive)

        def curFileHashGenerator():
            for curFile in localFiles:
                yield localFileHash(curFile), curFile

        stats = {}

        for objID in objIDList:

            obj = self.getObject(objID)

            objHashDict = {f.fileHashCode : f.selfUrl
                       for f in self.getObjectFiles(obj)}

            completed, matchingFolder, filesNotDownloaded, filesNotUploaded = \
                compareHashDictPair(objHashDict, curFileHashGenerator(),
                                   matchOnlyFirstHash=matchOnlyFirstHash,
                                   matchNumberFiles = matchNumberFiles)

            numMatchingFiles = sum(matchingFolder.values())
            numFilesNotUploaded = len(filesNotUploaded)
            numFilesNotDownloaded = len(filesNotDownloaded)

            logger.info("Checked obj %s:\t"
                        "%s matching files \t%s extra local files\t%s missing files"
                        %(objID, numMatchingFiles, numFilesNotUploaded, numFilesNotDownloaded ))
            logger.info("Matching files in folder: %s" %matchingFolder)
            stats[objID] = (completed, matchingFolder, filesNotDownloaded, filesNotUploaded)

        return stats


    def walkFolders(self, folderUrl, topdown=True):
        #folderID = self.getFolderByName(searchName)
        #
        # genearator similar to os.walk

        folder = self.getFolder(folderUrl)

        dirs = folder.childFolders
        nondirs = folder.containedObjects

        dir_urls = [] if dirs is None else [ i['selfUrl'] for i in dirs]
        nondir_urls = [] if nondirs is None else [i['selfUrl'] for i in nondirs]

        yield folder, dir_urls, nondir_urls

        for name in dir_urls:
            yield from self.walkFolders(name)

        if not topdown:
            yield  folder, dir_urls, nondir_urls

class compareLocalSystemToVSD(object):

    def __init__(self, folder, api, **kwargs):
        self.folder = folder
        #self.LocalHashDict = {localFileHash(f) : f for f in iterateFolderContent(folder, **kwargs)}
        self.api = api


    # def searchVSDObj(self, objID):
    #     obj = self.api.getObject(objID)
    #     objHashDict = {f.fileHashCode: f.selfUrl
    #                    for f in self.api.getObjectFiles(obj)}
    #     completed, matchingFolder, filesNotDownloaded, filesNotUploaded = \
    #         compareHashDictPair(objHashDict, self.LocalHashDict.iteritems())
    #     return

    @staticmethod
    def urlListFromContainer(container):
        #sometimes  olderObj.childFolders is None
        if container is None:
            return []
        else:
            return [i['selfUrl'] for i in container]

    @classmethod
    def getObjectAsRecord(cls, api, apiObject, returnHeader=False):
        if isinstance(apiObject, str):
            apiObject = api.getObject(apiObject)
        if returnHeader:
            objectDict = dict()
            nfiles = 0
            file0 = dict()
        else:
            objectDict = apiObject.get()
            files = objectDict.get('files', [])
            nfiles = files.get('totalCount',0)
            file0 = api.getFile(cls.urlListFromContainer(files['items'])[0]).get()

        fields = ['id',
                  'name',
                  'description',
                  'downloadUrl',
                  'sliceThickness',
                  'modality',
                  'segmentationMethod']
        record = {k : objectDict.get(k) for k in fields}
        record['type'] = objectDict.get('type', {}).get('name')
        record['nfiles'] = nfiles
        record['hash_0'] = file0.get('fileHashCode')
        fn0 = file0.get('originalFileName')
        record['originalFilename_0'] = fn0
        record['approxSize'] = nfiles * file0.get('size',0)
        return record

    def matchObjectsToLocalFolder(self,  items, onName = True, onHash=False):
        rootFolder = self.folder
        #items = self.getAllUnpublishedObjects()
        objectsCollection = self.buildObjectsCollections(items)
        n = len(objectsCollection['id'])
        objectsCollection['localFolder'] = [None] * n
        objectsCollection['local_nfiles'] = [None] * n

        for root, dirs, names in os.walk(rootFolder, topdown=False):
            nFiles = len(names)
            if nFiles > 0:
                for f in names:
                    try:
                        if onName:
                            i = objectsCollection['originalFilename_0'].index(f)
                        if onHash:
                            lh = localFileHash(f)
                            i = objectsCollection['hash_0'].index(lh)
                        objectsCollection['localFolder'][i] = root
                        objectsCollection['local_nfiles'][i] = len(names)
                        break
                    except ValueError:
                        pass
            try:
                firstMissingObject =  objectsCollection['localFolder'].index(None)
            except ValueError:
                return objectsCollection
        return objectsCollection

    def buildObjectsCollections(self, itemsIterable):
        objectsCollections = { k : []
                              for k in self.getObjectAsRecord(self.api,None, returnHeader = True).keys()
                              }
        for item in itemsIterable:
            record = self.getObjectAsRecord(self.api,item)
            for k,v in record.items():
                objectsCollections[k].append(v)
        return objectsCollections

    @staticmethod
    def writeObjectsCollections(fd, objectsCollections):
        import csv
        w = csv.writer(fd)
        keys = objectsCollections.keys()
        w.writerow(keys)
        n = len(objectsCollections.values()[0])
        for i in range(n):
            w.writerow([objectsCollections[k][i] for k in keys])

def main():

    from pprint import pprint
    ## connect using credentials
    api= createReport(authtype = 'basic',
                                url='https://demo.virtualskeleton.ch/api/',
                                username= "demo@virtualskeleton.ch",
                                password = "demo")

    localFolder = r"E:\dev\registerFolders\Data"

    print("Info on unpublished data")

    unPublishedObjects = api.getAllUnpublishedObjects()
    # for i, obj in enumerate(unPublishedObjects):
    #     print("\t",i,obj)

    cl = compareLocalSystemToVSD('.',api)

    upi =  cl.buildObjectsCollections(unPublishedObjects)
    #cl.matchObjectsToLocalFolder(upi, onName=False, onHash=True)
    import pandas as pd




    allMyDataID = api.getFolderByName('MyData', mode='exact').selfUrl
    myData =  dict()
    items = []
    for folder, subFolder, objects in  api.walkFolders(allMyDataID):
        items.extend(objects)
        for item in objects:
            myData[item] = folder

    cl.matchObjectsToLocalFolder(items, onName=False, onHash=True)

    # myObjects = []
    # for folder, subFolder, objects in  api.walkFolders(allMyData):
    #     for item in objects:
    #         record = compareLocalSystemToVSD.getObjectAsRecord(api,item)
    #         record['folder'] = folder.name
    #         print(record.values(), sep=',')
    #         myObjects.append(item) # = record['hash_0']
    #
    # data = cl.buildObjectsCollections(myObjects)
    #
    #
    # print("Scanning content of local folder",  localFolder)
    # depth = 0
    # matching = []
    # for root, dirs, files in os.walk(localFolder, topdown=False):
    #     imageFiles = list(filterImageFiles(files))
    #     nImages = len(imageFiles)
    #     if nImages:
    #         imageCounter = Counter([fileExtension(f) for f in imageFiles])
    #         tree = root.split(os.path.sep)
    #         curDepth = len(tree)
    #         baseDir = tree[-1]
    #         if curDepth > depth:
    #             depth = curDepth
    #
    #         print("\t".join(  [
    #                   "%s Files" % sum(imageCounter.values()),
    #                   str(dict(imageCounter)),
    #                   baseDir,
    #                   "\trootDir:"
    #                   ] +
    #                   tree[:-1] +
    #                   ['']*(depth-curDepth+1) ))
    #
    #         for curFile in imageFiles:
    #             curHash = localFileHash(curFile)
    #             try:
    #                 found = data['hash_0'].index(curHash)
    #                 matching.append((curFile,data['id'], root))
    #                 print(matching[-1])
    #                 if fileExtension(curFile) in ['', '.dcm'] and  len(imageCounter) == 1:
    #                     break
    #             except:
    #                 pass
    #
    #
    #
    #
    #
    # report = compareLocalSystemToVSD(localFolder, api)
    # result = report.matchObjectsToLocalFolder(api.getFolderByName('MyData', mode='exact').selfUrl, myObjects.keys(), onName=False, onHash=True)
    # idList = result['id']
    # localFolder = result['localFolder']
    #
    # for i, l  in zip(idList, localFolder):
    #     print(i,l)
    #     #print(result['id'][i], result['local_nfiles'][i])
    #
    #
    #


    # for folder, dirs, names in api.walkFolders(folderID):
    #     print("***",folder.name, folder.selfUrl,"***")
    #     for url in names:
    #         complete, matchfolders, filesNotUploaded, filesNotDownloaded = api.checkLocalFolder_vs_ID("/home/ubuntu/Downloads", url, excludePattern=".gz")
    #         print("Local content of", folder.name,)
    #         pprint(matchfolders,indent = 2)
    #         if not complete:
    #             logger.warning("Not complete!  %s" %folder.name,)
    #             print (folder.name,"\tMissing Files:", filesNotDownloaded)



if __name__ == '__main__':
    logging.basicConfig(level="INFO")
    main()


