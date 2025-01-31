def importBPY():
    import bpy
    print("Imported bpy correctly")
    # Get an example option from bpy
    print(bpy.context.preferences.addons.keys())


def importBlendFile():
    import bpy
    
    bpy.ops.wm.open_mainfile(filepath="/home/lorenzo/Downloads/BlenderFiles/scene.blend")
    print("Opened file correctly")

