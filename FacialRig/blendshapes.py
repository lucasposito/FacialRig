from maya.api import OpenMaya
from maya import cmds, mel

from .unplug_attr import Unplugged

import json
from pathlib import Path


with open(str(Path(__file__).parent / 'blendshapes.json'), 'r') as f:
    blendshapes = json.loads(f.read())


class BlendShapeData:
    NAME = 'core_blendshapes'
    BASE = blendshapes['base']
    SHAPES = blendshapes['shapes']
    CORRECTIVES = blendshapes['correctives']
    BLENDSHAPES = blendshapes['blendshapes']
    MASKS = blendshapes['masks']


def get_blendshape(mesh):
    """_summary_

    Args:
        mesh (str): Transform node or shape node name of the mesh

    Returns:
        str: Returns the blendshape node if there's any connected to the mesh
    """
    dag = OpenMaya.MSelectionList().add(mesh).getDagPath(0)
    obj = OpenMaya.MFnMesh(dag).object()

    blend_node = None
    dag_iter = OpenMaya.MItDependencyGraph(obj,
                                           OpenMaya.MItDependencyGraph.kDownstream,
                                           OpenMaya.MItDependencyGraph.kPlugLevel)
    while not dag_iter.isDone():
        current_item = dag_iter.currentNode()
        if current_item.hasFn(OpenMaya.MFn.kBlendShape):
            blend_node = OpenMaya.MFnDependencyNode(current_item).name()
            break
        dag_iter.next()
    return blend_node


class BlendShape:
    def __init__(self, main_mesh, masks, global_scale=1.0):
        main_mesh = OpenMaya.MSelectionList().add(main_mesh).getDagPath(0)
        self.main_mesh = OpenMaya.MFnMesh(main_mesh)

        self.current_scale = global_scale

        self.blend_node = get_blendshape(self.main_mesh.name())

        self.masks_data = masks
        self.shapes = dict()
        self.correctives = dict()

    @staticmethod
    def flip_symmetry(mesh, global_scale=1.0):
        mesh_list = OpenMaya.MSelectionList().add(mesh)
        mesh_mfn = OpenMaya.MFnMesh(mesh_list.getDagPath(0))

        edge_iter = OpenMaya.MItMeshEdge(mesh_list.getDependNode(0))
        central_edge = None
        central_vtx = None

        while not edge_iter.isDone():
            vtx_1, vtx_2 = edge_iter.vertexId(0), edge_iter.vertexId(1)

            point_1 = mesh_mfn.getPoint(vtx_1, OpenMaya.MSpace.kWorld)
            point_2 = mesh_mfn.getPoint(vtx_2, OpenMaya.MSpace.kWorld)

            min, max = -0.01, 0.01

            if min <= point_1[0] <= max and min <= point_2[0] <= max:
                central_edge = f'{mesh}.e[{edge_iter.index()}]'
                central_vtx = vtx_1
                break
            edge_iter.next()

        if not central_edge:
            return

        cmds.select(central_edge, r=True)
        mel.eval('activateTopoSymmetry("{0}", {{"{1}.vtx[*]"}}, {{"{2}"}}, "vertex", "dR_symmetryFlip", 1);'.format(
            central_edge, mesh, mesh))
        cmds.select(cl=True)

        offset = mesh_mfn.getPoint(central_vtx, OpenMaya.MSpace.kWorld)[0] * -1
        offset *= global_scale

        cmds.xform(mesh, t=[offset, 0, 0])
        cmds.makeIdentity(mesh, a=True, t=True)
        cmds.xform(ztp=True)

    @staticmethod
    def get_vertices_offset(base_mesh, target_mesh):
        # base_mesh and target_mesh should match vertex IDs

        base_mesh = OpenMaya.MSelectionList().add(base_mesh).getDependNode(0)
        target_mesh = OpenMaya.MSelectionList().add(target_mesh).getDependNode(0)

        offset_vtx = dict()

        base_vtx_iter = OpenMaya.MItMeshVertex(base_mesh)
        target_vtx_iter = OpenMaya.MItMeshVertex(target_mesh)

        while not base_vtx_iter.isDone() and not target_vtx_iter.isDone():
            offset = base_vtx_iter.position() - target_vtx_iter.position()
            if not all(value == 0 for value in offset):
                offset_vtx[base_vtx_iter.index()] = offset
            base_vtx_iter.next()
            target_vtx_iter.next()

        return offset_vtx

    @staticmethod
    def subtract_offset(corrective_mesh, offset):
        dag_obj = OpenMaya.MSelectionList().add(corrective_mesh).getDagPath(0)
        mfn_mesh = OpenMaya.MFnMesh(dag_obj)

        for vtx, vector in offset.items():
            result = mfn_mesh.getPoint(vtx) + vector
            mfn_mesh.setPoint(vtx, result)

    def get_mask_plug(self, shape_index):
        blend_node = OpenMaya.MSelectionList().add(self.blend_node).getDependNode(0)
        blend_node = OpenMaya.MFnDependencyNode(blend_node)

        first_plug = blend_node.findPlug('inputTarget', False)
        target_plug = first_plug.elementByLogicalIndex(0)
        group_plug = target_plug.child(0)

        shape_plug = group_plug.elementByLogicalIndex(shape_index)
        return shape_plug.child(1)

    def set_mask(self, name, shape_index):
        plug = self.get_mask_plug(shape_index)
        for vtx, value in self.masks_data[name].items():
            plug.elementByLogicalIndex(int(vtx)).setDouble(float(value))

    def set_combination_shape(self, name, shape_index, driver_targets):
        first_target, sec_target = driver_targets

        # TODO: edit corrective shapes before assigning the blendshape

        cmds.blendShape(self.blend_node, edit=True, t=[self.main_mesh.name(), shape_index, name, 1.0])
        cmds.combinationShape(bs=self.blend_node, cti=shape_index, cm=0, dti=[first_target, sec_target])

        blend_node = OpenMaya.MSelectionList().add(self.blend_node).getDependNode(0)
        blend_node = OpenMaya.MFnDependencyNode(blend_node)

        blend_plug = blend_node.findPlug('weight', False)
        shape_plug = blend_plug.elementByLogicalIndex(shape_index)

        if shape_plug.isDestination:
            first_target = blend_plug.elementByLogicalIndex(first_target)
            sec_target = blend_plug.elementByLogicalIndex(sec_target)
            self.correctives[name] = [first_target.partialName(useAlias=True), sec_target.partialName(useAlias=True)]

            comb_node = shape_plug.source().node()
            OpenMaya.MDGModifier().renameNode(comb_node, f'{name}_comb').doIt()

    def edit_corrective_shape(self, index, targets):
        if not isinstance(targets, list):
            targets = [targets]

        for target in targets:
            corrective_mesh = BlendShapeData.CORRECTIVES[index]
            target_mesh = BlendShapeData.SHAPES[target]
            print(corrective_mesh)
            print(target_mesh)
            self.subtract_offset(corrective_mesh, self.get_vertices_offset(self.main_mesh.name(), target_mesh))
        print('-----------')

    def create(self):
        # If the mesh shape is locked, it won't work
        if not self.blend_node:
            self.blend_node = cmds.blendShape(self.main_mesh.name(), n=BlendShapeData.NAME)[0]

        for index, shape in BlendShapeData.BLENDSHAPES.items():
            index = int(index)
            (shape_name,) = shape.keys()
            (values,) = shape.values()

            mask, main_shape, first_target, sec_target, flip = values
            self.shapes[shape_name] = index

            base_name = BlendShapeData.CORRECTIVES[main_shape] if sec_target else BlendShapeData.SHAPES[main_shape]
            base_shape = cmds.rename(base_name, f'{base_name}_temp')
            target_mesh = cmds.duplicate(base_shape, n=shape_name)[0]

            if flip:
                self.flip_symmetry(target_mesh, self.current_scale)

            if sec_target:
                self.set_combination_shape(shape_name, index, [first_target, sec_target])
            else:
                cmds.blendShape(self.blend_node, edit=True, t=[self.main_mesh.name(), index, target_mesh, 1.0])

            cmds.delete(target_mesh)
            cmds.rename(base_shape, base_name)

            self.set_mask(BlendShapeData.MASKS[mask], index)

            # TODO: set the shape in edit mode when adding combination shape

    def duplicate_n_apply_masks(self):
        blend_node = OpenMaya.MSelectionList().add(self.blend_node).getDependNode(0)
        blend_node = OpenMaya.MFnDependencyNode(blend_node)

        plug = blend_node.findPlug('weight', False)

        data = dict()
        
        for j in range(plug.numElements()):
            shape = plug.elementByPhysicalIndex(j).partialName(useAlias=True)
            index = plug.elementByPhysicalIndex(j).logicalIndex()

            with Unplugged(blend_node.name(), index, plug):
                plug.elementByPhysicalIndex(j).setFloat(1)
                data[shape] = self.main_mesh.getPoints()
                plug.elementByPhysicalIndex(j).setFloat(0)

        main_mesh = OpenMaya.MFnTransform(self.main_mesh.parent(0))
        main_mesh.findPlug('visibility', False).setBool(True)

        duplicated_mesh = cmds.duplicate(main_mesh.name(), n=f'{main_mesh.name()}_copy')[0]
        temp_blend_node = cmds.blendShape(duplicated_mesh)[0]

        for i, shape in enumerate(data.items()):
            in_scene = None
            if cmds.objExists(shape[0]):
                in_scene = cmds.rename(shape[0], 'temp')

            duplicated_temp = cmds.duplicate(duplicated_mesh, n=shape[0])[0]
            temp_dag = OpenMaya.MSelectionList().add(duplicated_temp).getDagPath(0)
            temp = OpenMaya.MFnMesh(temp_dag)

            temp.setPoints(map(OpenMaya.MPoint, shape[-1]))

            cmds.blendShape(temp_blend_node, edit=True, t=[duplicated_mesh, i, temp_dag.fullPathName(), 1.0])
            cmds.delete(temp_dag.fullPathName())
            if in_scene:
                cmds.rename(in_scene, shape[0])

        return duplicated_mesh
