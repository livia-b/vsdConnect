import os

from vsdConnect import models
import logging
logger = logging.getLogger(__name__)

def containedObjectsPreviewToDisk(c,folderData, outputfolder, name):
    for object in folderData.containedObjects:
        objId = os.path.basename(object.selfUrl)
        for i, preview in enumerate(c.getObject(object.selfUrl).objectPreviews):
            p_obj = models.APIPreview(**c.getRequest(preview.selfUrl))
            c._download(p_obj.imageUrl, os.path.join(outputfolder, "%s_%s_%02d.jpg" % (name, objId, i)))


def flattenDictFields(connector, dictRecord, prefix ='.',
                      ignorekeys= ('selfUrl'),
                      paginationPreview = True, ignoreLists = True, sortFields = False,
                      maxdepth=3  # with ontology items I can go in recursion
                      ):
    logger.debug(prefix)
    fields = {}
    sep = '_'
    if len(prefix.split(sep)) > maxdepth:
        logger.debug("max depth reached %s" %prefix)
        return fields

    if paginationPreview and 'pagination' in dictRecord:
        fields[prefix+'tot'] = dictRecord.get('totalCount')
        item1 = connector._get(dictRecord['items'][0]['selfUrl'])
        fields.update(flattenDictFields(connector,item1, prefix + 'item1_'))
        return fields

    for fieldKey, fieldContent in dictRecord.items():
        if fieldKey not in ignorekeys:
            if ignoreLists and isinstance(fieldContent,list):
                continue
            if isinstance(fieldContent, dict):
                nextPrefix = prefix + fieldKey + sep
                nextFields = flattenDictFields(connector, fieldContent, prefix = nextPrefix, ignorekeys = ignorekeys,
                                                         sortFields=False, maxdepth=maxdepth)
                fields.update(nextFields)
            else:
                fields[prefix+fieldKey] = fieldContent
    if sortFields:
        from collections import OrderedDict
        sortedColumns = sorted(["%02d_%s" % (len(i.split('_')), i) for i in fields.keys()])
        columns = [i[len("%02d_"%0):] for i in sortedColumns]
        unsortedFields = fields
        fields = OrderedDict([(k, unsortedFields[k]) for k in columns ])
    return fields