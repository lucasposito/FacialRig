from maya.api import OpenMaya


def get_vertices_offset(base_mesh, target_mesh):
    # base_mesh and target_mesh should match vertex IDs

    # iterate through vtx in both base_mesh, target_mesh
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


def subtract_offset(corrective_mesh, offset):
    dag_obj = OpenMaya.MSelectionList().add(corrective_mesh).getDagPath(0)
    mfn_mesh = OpenMaya.MFnMesh(dag_obj)

    for vtx, vector in offset.items():
        result = mfn_mesh.getPoint(vtx) + vector
        mfn_mesh.setPoint(vtx, result)



base_mesh = 'base'
corrective_shape = 'corrective'

for target in ['target_a', 'target_b']:
    subtract_offset(corrective_shape, get_vertices_offset(base_mesh, target))
