import os

from vsdConnect import models


def containedObjectsPreviewToDisk(c,folderData, outputfolder, name):
    for object in folderData.containedObjects:
        objId = os.path.basename(object.selfUrl)
        for i, preview in enumerate(c.getObject(object.selfUrl).objectPreviews):
            p_obj = models.APIPreview(**c.getRequest(preview.selfUrl))
            c._download(p_obj.imageUrl, os.path.join(outputfolder, "%s_%s_%02d.jpg" % (name, objId, i)))