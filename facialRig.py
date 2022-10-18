from maya.api import OpenMaya
from PySide2 import QtCore
from maya import cmds

from . import mayaData
from . import util

import math
import json


def find_meshes(parent_group, name_length):
    """
    Each part of the head meshes has the following name structure:
        'Mesh_HQ_BaseBody_BaseHead_EyeLeft'
    And only the head itself isn't defined:
        'Mesh_HQ_BaseBody_BaseHead'
    So the only way to distinguish it is by the shorter "split('_') block" length

    :return: dict meshes {EyeLeft: OpenMaya.MObject}
    """
    mesh_grp = OpenMaya.MSelectionList().add(parent_group).getDependNode(0)

    dag_iter = OpenMaya.MItDag()
    dag_iter.reset(mesh_grp, OpenMaya.MItDag.kDepthFirst, OpenMaya.MFn.kMesh)

    meshes = dict()
    while not dag_iter.isDone():
        node_mfn = OpenMaya.MFnDagNode(dag_iter.currentItem())
        parent_obj = node_mfn.parent(0)

        if parent_obj not in meshes.values():
            mfn = OpenMaya.MFnTransform(parent_obj)
            mesh_name = mfn.partialPathName().split(':')[-1]
            mesh_name = mesh_name.split('_')

            if len(mesh_name) < name_length:
                mesh_name.append(mayaData.CONST.MESHES[0])
            meshes[mesh_name[-1]] = parent_obj
            dag_iter.next()
            continue
        dag_iter.next()
    return meshes


class SceneSetup(object):
    def __init__(self, target_file):
        if target_file.endswith("fbx"):
            cmds.file(target_file, r=True, iv=True, ns=mayaData.CONST.EXPORT_NAMESPACE, type="fbx", gr=True,
                      gn=mayaData.CONST.TEMP_EXPORT_GRP, mnc=True)
            cmds.file(target_file, ir=True, iv=True)
        else:
            # TODO: If it's not fbx it's going to be mayaData
            cmds.file(target_file, i=True, ns=mayaData.CONST.EXPORT_NAMESPACE, type="fbx", gr=True,
                      gn=mayaData.CONST.TEMP_EXPORT_GRP, iv=True, mnc=True)


class FacialRigData(mayaData.BaseData):
    def __init__(self):
        super(FacialRigData, self).__init__()
        self['face_matrix_offset'] = list()
        self['head_matrix_offset'] = list()
        self['anchor_matrix'] = list()

        self['meshes'] = dict()  # 'Head': mayaData, 'EyeLeft': mayaData
        self['uv'] = dict()
        self['material'] = dict()
        self['joints'] = dict()
        self['skin'] = dict()

        self['facial_board'] = dict()

        self['driven_keys'] = dict()
        self['blend_shapes'] = dict()
        self['logic'] = dict()

        self['empty'] = True


class FacialRig(object):
    def __init__(self):
        """
        Only two things are needed to build the whole rig:
        1- Static anchor mesh to know the matrix
        1- Head join to parent everything under
        """
        self.head_joint_orientation = (-90, 0, 90)
        self.facial_skin = 'default'
        self.rig = FacialRigData()

    def read_data(self):
        self.rig = FacialRigData()
        # Serializing the mayaData in 2 steps: Mesh, Facial Board, Face Joints, Driven Key
        # Step 1: MESH
        for mesh, obj in find_meshes(mayaData.CONST.MESH_GRP, 6).items():
            self.rig['meshes'][mesh] = mayaData.geometry.get(OpenMaya.MFnTransform(obj).partialPathName())
            self.rig['uv'][mesh] = mayaData.uv.get(OpenMaya.MFnTransform(obj).partialPathName())
            self.rig['material'][mesh] = mayaData.material.get(OpenMaya.MFnTransform(obj).partialPathName())

        if not self.rig['meshes']:
            OpenMaya.MGlobal.displayError('The group {} is empty'.format(mayaData.CONST.MESH_GRP))
            return

        anchor_matrix = util.pivot.matrix_between_vertices(self.rig['meshes'][mayaData.CONST.ANCHOR_MESH]['name'])

        face_offset = OpenMaya.MSelectionList().add(mayaData.CONST.DRIVEN_KEY_JNT).getDagPath(0)
        self.rig['face_matrix_offset'].extend(list(anchor_matrix * face_offset.inclusiveMatrix().inverse()))

        head_offset = OpenMaya.MSelectionList().add(mayaData.CONST.ANCHOR_JNT).getDagPath(0)
        self.rig['head_matrix_offset'].extend(list(anchor_matrix * head_offset.inclusiveMatrix().inverse()))

        self.rig['anchor_matrix'].extend(list(anchor_matrix))

        # Step 2: Driven Key Joints
        self.rig['driven_keys'] = mayaData.drivenKey.get(mayaData.CONST.BASE_NODE, mayaData.CONST.DRIVEN_KEY_JNT)
        # Skeleton is not needed as facial joints come from face skin file

        # Step 3: Face Board
        self.rig['facial_board'] = mayaData.facialBoard.get()

        # Step 4: Joints
        anchor_obj = OpenMaya.MSelectionList().add(mayaData.CONST.DRIVEN_KEY_JNT).getDependNode(0)
        anchor_mfn = OpenMaya.MFnTransform(anchor_obj)
        parent_obj = anchor_mfn.parent(0)

        OpenMaya.MDagModifier().reparentNode(anchor_obj).doIt()
        self.rig['joints'] = mayaData.skeleton.get(anchor_mfn.fullPathName())
        OpenMaya.MDagModifier().reparentNode(anchor_obj, parent_obj).doIt()

        self.rig['empty'] = False

    def build_data(self, reload_data=None, target_rig=None):
        if reload_data:
            self.rig = FacialRigData()
            self.rig.update(reload_data)

        if self.rig['empty']:
            return

        radians = [math.radians(x) for x in self.head_joint_orientation]
        head_orient = OpenMaya.MEulerRotation(radians)
        matrix_mfn = OpenMaya.MTransformationMatrix(OpenMaya.MMatrix.kIdentity)
        matrix_mfn.rotateBy(head_orient, OpenMaya.MSpace.kWorld)
        origin = OpenMaya.MMatrix(self.rig['head_matrix_offset']) * matrix_mfn.asMatrix()

        # importing the target meshes
        if target_rig:
            SceneSetup(target_rig)
            # TODO: Work on the replacement of this target mesh with the old tier mesh
            for mesh, obj in find_meshes(mayaData.CONST.TEMP_EXPORT_GRP, 5).items():
                # here is the place to manipulate the target meshes
                # self.rig['meshes'][mesh] = mayaData.geometry.get(obj.partialPathName())
                if mesh == mayaData.CONST.ANCHOR_MESH:
                    origin = util.pivot.matrix_between_vertices(OpenMaya.MFnTransform(obj).fullPathName())

        # Step 0: FOLDER STRUCTURE
        try:
            mesh_grp = OpenMaya.MSelectionList().add(mayaData.CONST.MESH_GRP).getDependNode(0)
            joint_grp = OpenMaya.MSelectionList().add(mayaData.CONST.JOINT_GRP).getDependNode(0)
        except RuntimeError:
            mod = OpenMaya.MDagModifier()
            character_grp = mod.createNode('transform', OpenMaya.MObject.kNullObj)
            mesh_grp = mod.createNode('transform', OpenMaya.MObject.kNullObj)
            joint_grp = mod.createNode('transform', OpenMaya.MObject.kNullObj)

            mod.renameNode(character_grp, mayaData.CONST.MESH_GRP.split('|')[0])
            mod.renameNode(mesh_grp, mayaData.CONST.MESH_GRP.split('|')[-1])
            mod.renameNode(joint_grp, mayaData.CONST.JOINT_GRP.split('|')[-1])

            mod.reparentNode(mesh_grp, character_grp)
            mod.reparentNode(joint_grp, character_grp)

            mod.doIt()

        # Step 1: MESH
        for mesh, uv in zip(self.rig['meshes'].values(), self.rig['uv'].values()):
            try:
                OpenMaya.MSelectionList().add(mesh['name'])
            except RuntimeError:
                mayaData.geometry.load(mesh)
                mayaData.uv.load(uv)
                mod = OpenMaya.MDagModifier()
                mesh_obj = OpenMaya.MSelectionList().add(mesh['name']).getDependNode(0)
                mod.reparentNode(mesh_obj, mesh_grp)
                mod.doIt()
                cmds.makeIdentity(mesh['name'], a=True, n=False, pn=True, t=True, r=True)

                anchor_matrix = OpenMaya.MMatrix(self.rig['anchor_matrix'])
                util.pivot.match_transformations(anchor_matrix, mesh['name'])

                mat = OpenMaya.MTransformationMatrix(origin)
                OpenMaya.MFnTransform(mesh_obj).setTransformation(mat)
                cmds.makeIdentity(mesh['name'], a=True, n=False, pn=True, t=True, r=True)
                cmds.xform(mesh['name'], ztp=True)
                continue

            print('{} is already in the scene'.format(mesh['name']))
            # TODO: replace only the mesh without touching other mayaData

        # Step 2: Joints
        mayaData.skeleton.load(self.rig['joints'])
        driven_key_jnt = OpenMaya.MSelectionList().add(mayaData.CONST.DRIVEN_KEY_JNT).getDependNode(0)

        face_matrix = OpenMaya.MMatrix(self.rig['face_matrix_offset']).inverse() * origin
        face_matrix = OpenMaya.MTransformationMatrix(face_matrix)

        OpenMaya.MDagModifier().reparentNode(driven_key_jnt, joint_grp).doIt()
        OpenMaya.MFnTransform(driven_key_jnt).setTransformation(face_matrix)

        # Step 3: Face Board
        mayaData.facialBoard.load(self.rig['facial_board'])
        facial_board = OpenMaya.MSelectionList().add(mayaData.CONST.FACIAL_BOARD).getDependNode(0)

        distance = face_matrix.translation(OpenMaya.MSpace.kWorld) + OpenMaya.MVector(15, 0, 0)
        OpenMaya.MFnTransform(facial_board).setTranslation(distance, OpenMaya.MSpace.kTransform)

        cmds.parentConstraint(mayaData.CONST.DRIVEN_KEY_JNT, mayaData.CONST.FACIAL_BOARD, mo=True)

        # Step 4: Driven Keys
        mayaData.drivenKey.load(self.rig['driven_keys'], face_matrix.asMatrix())

        # Step 5: Facial Joints
        facial_joints = self.get_facial_base('joints')
        facial_skin = self.get_facial_base('skin')
        if facial_joints:
            mayaData.facialJoints.load(self.rig['meshes'][mayaData.CONST.ANCHOR_JNT]['name'], facial_joints)
        if facial_skin:
            mayaData.skin.load(facial_skin, self.rig['meshes'][mayaData.CONST.ANCHOR_JNT]['name'])

        # Step 6: Blendshapes
        # Step 7: Network

    def get_facial_base(self, part):
        facial_path = QtCore.QDir('{}\\faces'.format(mayaData.CONST.MAIN_PATH))

        name = '_'.join([self.facial_skin, part]) + '.json'
        for each in facial_path.entryList():
            if each != name:
                continue

            file_path = '{}/{}'.format(facial_path.path(), name)
            with open(file_path, 'r') as f:
                return json.loads(f.read())

        OpenMaya.MGlobal.displayError('{} is the file you\'re looking for and it\'s not being found'.format(name))

    def save_data(self):
        self.rig.save()

    def solve_rig(self):
        # Step 1: Animation
        # Step 2: Merge skin
        # Step 3: Solver
        pass
