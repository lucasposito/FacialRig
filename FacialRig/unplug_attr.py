from maya.api import OpenMaya


class Unplugged(object):
    def __init__(self, node, attrs, plug=None):
        """
        This class takes a node and a list of its own attributes,
        eg. with TempDisconnectAttrs('pCube1', ['translateX', 'translateY', 'translateZ'])
        when entering the with statement it will unlock any locked attributes,
        disconnect them from any input nodes and connect these inputs to a temp node.
        When exiting it reconnects it all over again, locks the attributes back and deletes the temp node.
        It's useful if you want to manipulate the node's attributes to see how the output will behave
        without the influence of any source connections into the node.

        :param node: str node or list of nodes
        :param attrs: list attributes
        """
        if not isinstance(node, list):
            node = [node]
        
        if not isinstance(attrs, list):
            attrs = [attrs]

        self.attrs = list()
        for n in node:
            n = OpenMaya.MSelectionList().add(n).getDependNode(0)
            if plug:
                self.attrs.extend([plug.elementByPhysicalIndex(x) for x in attrs])
                continue
            self.attrs.extend([OpenMaya.MFnDependencyNode(n).findPlug(x, False) for x in attrs])

        self.locked_attrs = [x for x in self.attrs if x.isLocked]
        self.connection_table = list()
        self._temp_node = None

    def __enter__(self):
        for x in self.locked_attrs:
            x.isLocked = False
        self.disconnect()

    def __exit__(self, typ, value, traceback):
        for attr in self.attrs:
            inputs = attr.source()
            if not inputs.isNull:
                OpenMaya.MDGModifier().disconnect(inputs, attr).doIt()
        self.reconnect()
        for x in self.locked_attrs:
            x.isLocked = True
        OpenMaya.MDGModifier().deleteNode(self._temp_node).doIt()

    def disconnect(self):
        modifier = OpenMaya.MDagModifier()
        self._temp_node = modifier.createNode("transform", OpenMaya.MObject.kNullObj)
        modifier.doIt()

        for i, attr in enumerate(self.attrs):
            inputs = attr.source()
            if inputs.isNull:
                continue
            num_attr = OpenMaya.MFnNumericAttribute()
            attr_obj = num_attr.create("attr%d" % i, "attr%d" % i, OpenMaya.MFnNumericData.kFloat, 0.0)
            num_attr.keyable = True

            mod = OpenMaya.MDGModifier()
            mod.addAttribute(self._temp_node, attr_obj)
            mod.doIt()

            plug = OpenMaya.MFnTransform(self._temp_node).findPlug(attr_obj, False)

            OpenMaya.MDGModifier().connect(inputs, plug).doIt()
            OpenMaya.MDGModifier().disconnect(inputs, attr).doIt()

            self.connection_table.append([inputs, attr, plug])

    def reconnect(self):
        for source, destination, temp_attr in self.connection_table:
            OpenMaya.MDGModifier().connect(source, destination).doIt()
            OpenMaya.MDGModifier().disconnect(source, temp_attr).doIt()
