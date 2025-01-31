def importBPY():
    import bpy
    print("Imported bpy correctly")
    # Get an example option from bpy
    print(bpy.context.preferences.addons.keys())
    