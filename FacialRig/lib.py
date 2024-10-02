from maya.api import OpenMaya, OpenMayaAnim
from maya import cmds

import math
import copy
import pandas as pd

import MayaData
import dem_bones


def create_facial_joints():
    playblast_options = {
        "format": "image",
        "compression": "jpg",
        "quality": 100,
        "width": 1920,
        "height": 1080,
        "forceOverwrite": True,
        "viewer": False,
        "framePadding": 4,
        "startTime": 1,
        "endTime": 1,
        "filename": "playblast_output"
    }

    # Perform playblast
    playblast_path = cmds.playblast(**playblast_options)


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
    """ This function gets the influences of a joint in the result mesh as a mask to subtract
        from every joints influence in the base mesh, where:
            - 0.0 removes the joint influence from the base mesh entirely.
            - 1.0 keeps the full joint influence from the base mesh.
        After applying the mask, the function removes the mask joint from the result mesh, combines
        the adjusted base mesh with the result mesh, and normalizes the combined weights so that
        the total influence for each vertex sums to 1.0.

    Args:
        base_mesh (str, OpenMaya.MObject): First Mesh
        result_mesh (str, OpenMaya.MObject): Second Mesh
        mask_jnt (str, OpenMaya.MObject): A joint part of First Mesh influences

    Returns:
        MayaData.skin.SkinData: mesh weights of mesh A (minus its given mask joint)
        and mesh B merged together
    """
    base_skin = pd.DataFrame(MayaData.skin.get(base_mesh))
    result_skin = pd.DataFrame(MayaData.skin.get(result_mesh))

    # Apply the mask to result_skin in a vectorized way
    mask = result_skin[mask_jnt].clip(0.0, 1.0)  # Get mask and clip values between 0.0 and 1.0
    base_skin = base_skin.multiply(mask, axis=0)  # Apply mask to all rows in result_skin

    result_skin.drop(columns=[mask_jnt], inplace=True)

    # Merge the DataFrames horizontally
    merged_skin = pd.concat([base_skin, result_skin], axis=1)

    # Normalize each row, so it sums to 1.0, adjusting the last element if necessary
    def normalize_row(row):
        total_sum = row.sum()
        if total_sum == 0:
            return row  # Skip rows that sum to 0
        normalized_row = row / total_sum  # Normalize the row
        normalized_row.iloc[-1] += 1.0 - normalized_row.sum()  # Adjust last element to sum exactly to 1.0
        return normalized_row.round(4)  # Round to 4 decimal places

    merged_skin = merged_skin.apply(normalize_row, axis=1)

    return merged_skin.to_dict(orient='list')


def run_dembones(blendshape_mesh, skinned_mesh, total_frame):
    OpenMaya.MGlobal.displayInfo('Starting Dembones')
    dembones = dem_bones.DemBones()
    dembones.compute(skinned_mesh, blendshape_mesh, start_frame=1, end_frame=total_frame)

    for frame in range(dembones.start_frame, dembones.end_frame + 1):
        for influence in dembones.influences:
            matrix = OpenMaya.MMatrix(dembones.anim_matrix(influence, frame))
            matrix = OpenMaya.MTransformationMatrix(matrix)
            translate = matrix.translation(OpenMaya.MSpace.kWorld)
            rotate = matrix.rotation().asVector()

            set_key(influence, 'tx', translate.x, frame)
            set_key(influence, 'ty', translate.y, frame)
            set_key(influence, 'tz', translate.z, frame)
            set_key(influence, 'rx', math.degrees(rotate.x), frame)
            set_key(influence, 'ry', math.degrees(rotate.y), frame)
            set_key(influence, 'rz', math.degrees(rotate.z), frame)

    skin_cluster_fn = OpenMayaAnim.MFnSkinCluster(MayaData.skin.get_skin_cluster(skinned_mesh))

    mesh_dag = OpenMaya.MSelectionList().add(skinned_mesh).getDagPath(0)
    mesh_dag.extendToShape()

    skin_cluster_fn.setWeights(
        mesh_dag,
        OpenMaya.MObject(),
        OpenMaya.MIntArray(range(len(dembones.influences))),
        OpenMaya.MDoubleArray(dembones.weights)
    )
    OpenMaya.MGlobal.displayInfo('Dembones Finished')

