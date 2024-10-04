# Facial Rig Tool
These are all the external libraries you’ll need:

- <a href="https://github.com/robertjoosten/maya-dem-bones"> Dembones </a>
- <a href="https://github.com/lucasposito/MayaData">MayaData</a>
- Numpy
- Pandas

Drag and drop the installation file into the Maya viewport, then run the command:

```
FacialRig.FaceUI.show_ui()
```

Save it as a shelf button for your convenience.

# Example
- Import FaceShapes_man.fbx or FaceShapes_ox.fbx example file into a Maya scene.
- Select "Head_Base" mesh and click "Load Base Head" in the Facial Tool.
- Click "Import" and select all the masks from the respective folder.
- Click "Create Rig".
