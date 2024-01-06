from maya.api import OpenMaya, OpenMayaAnim
from maya import cmds

import math
import copy
from pathlib import Path

import MayaData


def delete_all_keys(node):
    """Deletes all animation from a given node

    Args:
        node (str, OpenMaya.MObject): Desired node to delete animations
    """
    obj = OpenMaya.MSelectionList().add(node).getDependNode(0)
    mod = OpenMaya.MDagModifier()
    for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'visibility']:
        attr_plug = OpenMaya.MFnTransform(obj).findPlug(attr, False)
        anim_mfn = OpenMayaAnim.MFnAnimCurve()
        if not anim_mfn.hasObj(attr_plug.source().node()):
            continue
        mod.deleteNode(attr_plug.source().node())
    mod.doIt()


def set_key(node, attribute, value=None, frame=None):
    """Set a key using the Maya Api. It will delete the key if there's an existing key at the given frame.

    Args:
        node (str, OpenMaya.MObject, OpenMaya.MPlug): Transform Node, if a plug the attribute needs to be an Int index
        attribute (str or int): Name of the attribute, or Int Index if the given node is a plug
        value (float, optional): Desired value to key the given attribute. It keys the current value if None.
        frame (int, optional): Desired frame to key the given attribute. It keys the current frame if None.

    Returns:
        OpenMayaAnim.MFnAnimCurve: Returns the animation node if there's any, otherwise it returns None
    """
    unit_scale = {'mm': 0.1, 'cm': 1.0, 'm': 1e+2}
    unit_scale = unit_scale[cmds.currentUnit(q=True, linear=True)]
    
    current_time = OpenMayaAnim.MAnimControl.currentTime()
    if frame:
        current_time = OpenMaya.MTime(frame, OpenMaya.MTime.kNTSCFrame)

    if isinstance(node, OpenMaya.MPlug):
        plug = node.elementByPhysicalIndex(attribute)
    else:
        obj = OpenMaya.MSelectionList().add(node).getDependNode(0)
        plug = OpenMaya.MFnTransform(obj).findPlug(attribute, False)

    if value:
        if plug.partialName() in ['tx', 'ty', 'tz']:
            value *= unit_scale
        if plug.partialName() in ['rx', 'ry', 'rz']:
            value = math.radians(value)
        plug.setDouble(value)
    value = plug.asDouble()
    anim_obj = plug.source().node()
    anim_mfn = OpenMayaAnim.MFnAnimCurve()

    if anim_mfn.hasObj(anim_obj):
        anim_mfn.setObject(anim_obj)
    else:
        anim_mfn.create(plug, OpenMayaAnim.MFnAnimCurve.kAnimCurveUnknown)

    index = anim_mfn.find(current_time)
    if index is None:
        index = anim_mfn.insertKey(current_time)
        anim_mfn.setValue(index, value)
        return anim_mfn

    anim_mfn.remove(index)
    if anim_mfn.numKeys:
        return anim_mfn

    OpenMaya.MDagModifier().deleteNode(anim_obj).doIt()
    plug.setDouble(value)


def merge_skin(base_mesh, result_mesh, mask_jnt):
    """It takes the weight influences of a given joint and uses it as a mask to
    merge all the joints and weights of a result mesh onto the rest of
    joints and weights of a base mesh

    Args:
        base_mesh (str, OpenMaya.MObject): First Mesh
        result_mesh (str, OpenMaya.MObject): Second Mesh
        mask_jnt (str, OpenMaya.MObject): A joint part of First Mesh influences

    Returns:
        MayaData.skin.SkinData: mesh weights of mesh A (minus its given mask joint)
        and mesh B merged together
    """
    base_skin = MayaData.skin.get(base_mesh)
    result_skin = MayaData.skin.get(result_mesh)
    output_skin = {'weights': dict(), 'influences': copy.deepcopy(base_skin['influences'])}
    output_skin['max_influence'] = base_skin['max_influence']

    mfn_skin = OpenMaya.MSelectionList().add(result_skin['name']).getDependNode(0)
    mfn_skin = OpenMayaAnim.MFnSkinCluster(mfn_skin)

    jnt = OpenMaya.MSelectionList().add(mask_jnt).getDagPath(0)
    jnt_id = mfn_skin.indexForInfluenceObject(jnt)

    old_map = dict()

    total_jnts = len(base_skin['influences'].values())

    for index, name in result_skin['influences'].items():
        if index == jnt_id:
            continue
        output_skin['influences'][total_jnts] = name
        old_map[index] = total_jnts
        total_jnts += 1

    for base_inf, result_inf in zip(base_skin['weights'].items(), result_skin['weights'].values()):
        vtx_id, base_inf = base_inf

        output_vtx = dict()
        mask = 0.0
        for id, value in result_inf.items():
            value = round(value, 2)
            if id == jnt_id:
                mask = value
                continue
            if value > 0.0:
                output_vtx[old_map[id]] = value

        for id, value in base_inf.items():
            value = round(value, 2)
            value = value * (max(0.0, min(1.0, mask)))
            if value > 0.0:
                output_vtx[id] = value

        total_sum = sum(output_vtx.values())
        normalized_output = {key: round(value / total_sum, 4) for key, value in output_vtx.items()}
        output_skin['weights'][vtx_id] = normalized_output

    return output_skin


def run_dembones(mesh, total_frame, n_bones=81):
    """Runs a hda (Houdini) file that runs a dembones wrapped node.
    The given mesh needs to contain skinned joints, blendshapes and keyed animation

    Args:
        mesh (str): Mesh with blendshapes
        total_frame (int): Duration of the current Range of Motion animation
        n_bones (int, optional): number of bones to skin the output mesh to

    Returns:
        MayaData.skin.SkinData: mesh weights of the output mesh and the animated joints generated in the scene
    """

    cmds.loadPlugin('houdiniEngine', qt=True)
    file_path = str(Path(__file__).parent / 'RIG.SSDR.1.0.hda')
    houdini_node = cmds.houdiniAsset(loadAsset=[file_path, 'RIG::Object/SSDR::1.0'])

    # save mesh fbx
    input_path = Path.home() / 'input_mesh_temp.fbx'
    output_path = Path.home() / 'output_mesh_temp.fbx'

    cmds.select([mesh] + MayaData.skin.get_skin_joints(mesh), r=True)
    cmds.file(str(input_path), exportSelected=True, type='FBX Export', force=True)
    if 'FbxWarningWindow' in cmds.lsUI(wnd=True):
        cmds.deleteUI('FbxWarningWindow')
        cmds.refresh()

    # Execute SSDR
    cmds.setAttr(f'{houdini_node}.houdiniAssetParm_inputFbx', str(input_path).replace("\\", "/"), typ='string')
    cmds.setAttr(f'{houdini_node}.houdiniAssetParm_sOutputFile', str(output_path).replace("\\", "/"), typ='string')
    
    cmds.setAttr(f'{houdini_node}.houdiniAssetParm_f__tuple0', 0)
    cmds.setAttr(f'{houdini_node}.houdiniAssetParm_f__tuple1', total_frame)
    cmds.setAttr(f'{houdini_node}.houdiniAssetParm_nBones', n_bones)

    cmds.setAttr(f'{houdini_node}.houdiniAssetParm_reload__button', 1)

    for i in range(2):
        cmds.refresh()
        cmds.setAttr(f'{houdini_node}.houdiniAssetParm_execute__button', 1)
        cmds.dgeval(f"{houdini_node}.output")

    cmds.file(str(output_path), i=True, type="FBX", ignoreVersion=True, ra=True)

    output_mesh = 'groupdelete1'
    if not cmds.objExists(output_mesh):
        return
    
    skin = MayaData.skin.get(output_mesh)

    cmds.delete([output_mesh, houdini_node])
    return skin
