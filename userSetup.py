import maya.cmds as cmds


if not cmds.about(batch=True):
    cmds.evalDeferred('import FacialRig')
