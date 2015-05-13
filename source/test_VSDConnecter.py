import unittest
from unittest import TestCase
import connectVSD

__author__ = 'lbarazzetti'


class TestVSDConnecter(unittest.TestCase):
    def test_getObject(self):
        id = 121
        id_info = self.connector.getObject(id)
        for f in id_info.files[:3]:
            fileURL = f['selfUrl']
            file_info = self.connector.getRequest(fileURL)
        self.assertTrue(id_info)

    def _checkObjectInFolder(self,foldername,objecturl):
        folder = self.connector.getFolderByName(foldername)[0]
        objSelfUrl = dict([('selfUrl',objecturl,)])
        if folder.containedObjects:
            return objSelfUrl in folder.containedObjects
        else:
            return False

    def test_addObjectToFolder(self):
        foldername = 'test_folder2'
        id = 121
        folder = self.connector.getFolderByName(foldername)[0]
        obj = self.connector.getObject(id)
        self.connector.addObjectToFolder(folder, obj)
        self.assertTrue(self._checkObjectInFolder(foldername, obj.selfUrl))


    def test_getFolderByName(self):
        name = 'test_folder1'
        res = self.connector.getFolderByName(name[:-2])
        for folder in res:
            self.assertTrue(isinstance(folder, connectVSD.APIFolder  ) )
            self.assertTrue(folder.selfUrl)

    def setUp(self):
        default_kwarg = dict(
            url='https://demo.virtualskeleton.ch/api/',
            username="demo@virtualskeleton.ch",
            password="demo")
        self.connector = connectVSD.VSDConnecter(**default_kwarg)


if __name__ == '__main__':
    unittest.main()

