from abaqus import session
from abaqusConstants import *
from driverUtils import executeOnCaeStartup
import visualization
import os
import csv
import math
import traceback

executeOnCaeStartup()

odb_path = os.environ.get("ABAQUS_ODB_PATH", "").strip()
out_dir = os.environ.get("ABAQUS_POST_DIR", "").strip()

if not odb_path:
    raise RuntimeError("ABAQUS_ODB_PATH is missing.")

if not out_dir:
    raise RuntimeError("ABAQUS_POST_DIR is missing.")

if not os.path.isfile(odb_path):
    raise RuntimeError("ODB file not found: %s" % odb_path)

if not os.path.isdir(out_dir):
    os.makedirs(out_dir)

start_file = os.path.join(out_dir, "visualization_started.txt")
done_file = os.path.join(out_dir, "visualization_done.txt")
error_file = os.path.join(out_dir, "visualization_error.txt")
log_file = os.path.join(out_dir, "visualization_log.txt")


def log(msg):
    print(msg)
    f = open(log_file, "a")
    f.write(msg + "\n")
    f.close()


def save_displacement_png(vp, out_dir, file_stem, refinement_type, refinement_label):
    vp.odbDisplay.setPrimaryVariable(
        variableLabel='U',
        outputPosition=NODAL,
        refinement=(refinement_type, refinement_label)
    )
    session.printToFile(
        fileName=os.path.join(out_dir, file_stem),
        format=PNG,
        canvasObjects=(vp,)
    )
    log("[visualization.py] saved PNG: %s" % os.path.join(out_dir, file_stem + ".png"))


# reset log
f = open(log_file, "w")
f.write("=== visualization.py started ===\n")
f.close()

sf = open(start_file, "w")
sf.write("Visualization script started.\n")
sf.write("ODB: %s\n" % odb_path)
sf.close()

try:
    log("[visualization.py] ODB path = %s" % odb_path)
    log("[visualization.py] output dir = %s" % out_dir)

    # OPEN ODB
    log("[visualization.py] opening ODB...")
    odb = visualization.openOdb(path=odb_path)
    log("[visualization.py] ODB opened successfully")

    if len(session.viewports.keys()) == 0:
        vp = session.Viewport(name='Viewport: 1', origin=(0, 0), width=200, height=120) #modify for bigger image saving
        log("[visualization.py] created new viewport")
    else:
        vp = session.viewports[session.currentViewportName]
        log("[visualization.py] using current viewport: %s" % session.currentViewportName)

    vp.makeCurrent()
    vp.setValues(displayedObject=odb)
    vp.view.fitView()
    log("[visualization.py] viewport set and fitView applied")

    # WHITE BACKGROUND FOR SAVED PNG
    session.graphicsOptions.setValues(
        backgroundStyle=SOLID,
        backgroundColor='White'
    )

    session.printOptions.setValues(
        rendition=COLOR,
        vpDecorations=ON,
        vpBackground=ON
    )

    try:
        vp.viewportAnnotationOptions.setValues(
            triad=ON,
            title=ON,
            state=ON,
            compass=ON
        )
    except:
        pass

    log("[visualization.py] white background and print options applied")

    # LAST STEP / LAST FRAME
    step_names = list(odb.steps.keys())
    log("[visualization.py] step names = %s" % step_names)

    if len(step_names) == 0:
        raise RuntimeError("No step found in ODB.")

    step_index = len(step_names) - 1
    step_name = step_names[step_index]
    step_obj = odb.steps[step_name]
    log("[visualization.py] using last step = %s" % step_name)

    if len(step_obj.frames) == 0:
        raise RuntimeError("No frame found in the last step.")

    frame_index = len(step_obj.frames) - 1
    frame = step_obj.frames[frame_index]
    log("[visualization.py] number of frames in last step = %d" % len(step_obj.frames))
    log("[visualization.py] using last frame index = %d" % frame_index)

    vp.odbDisplay.setFrame(step=step_index, frame=frame_index)
    vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
    log("[visualization.py] frame set in viewport")

    # DISPLACEMENT FIELD
    field_names = list(frame.fieldOutputs.keys())
    log("[visualization.py] available field outputs = %s" % field_names)

    if 'U' not in frame.fieldOutputs.keys():
        raise RuntimeError("Displacement field U not found in ODB.")

    # show displacement magnitude in viewer
    vp.odbDisplay.setPrimaryVariable(
        variableLabel='U',
        outputPosition=NODAL,
        refinement=(INVARIANT, 'Magnitude')
    )
    log("[visualization.py] displacement field U set as primary variable")

    # SAVE PNGS
    log("[visualization.py] saving displacement PNGs...")

    save_displacement_png(vp, out_dir, "displacement_magnitude", INVARIANT, "Magnitude")
    save_displacement_png(vp, out_dir, "displacement_U1", COMPONENT, "U1")
    save_displacement_png(vp, out_dir, "displacement_U2", COMPONENT, "U2")

    try:
        save_displacement_png(vp, out_dir, "displacement_U3", COMPONENT, "U3")
    except Exception as e:
        log("[visualization.py] could not save U3 PNG: %s" % str(e))

    # NODE COORDINATE MAP
    node_coord_map = {}
    total_nodes = 0

    for inst_name, inst in odb.rootAssembly.instances.items():
        node_coord_map[inst_name] = {}
        for node in inst.nodes:
            coords = list(node.coordinates)
            while len(coords) < 3:
                coords.append(0.0)
            node_coord_map[inst_name][node.label] = coords
            total_nodes += 1

    log("[visualization.py] node coordinate map built")
    log("[visualization.py] total instances = %d" % len(odb.rootAssembly.instances))
    log("[visualization.py] total nodes = %d" % total_nodes)

    # EXPORT NODAL DISPLACEMENT DATA
    u_field = frame.fieldOutputs['U'].getSubset(position=NODAL)
    disp_csv = os.path.join(out_dir, "displacement_nodal_data.csv")

    log("[visualization.py] exporting nodal displacement CSV...")
    f = open(disp_csv, "w")
    writer = csv.writer(f)
    writer.writerow([
        "Instance", "NodeLabel", "X", "Y", "Z",
        "U1", "U2", "U3", "Magnitude"
    ])

    written_count = 0
    skipped_none_instance = 0
    skipped_missing_coord = 0
    max_mag = 0.0
    max_node = None

    for v in u_field.values:
        node_label = getattr(v, "nodeLabel", None)

        # Some Abaqus nodal values may not carry an instance object
        if getattr(v, "instance", None) is None:
            skipped_none_instance += 1
            log("[visualization.py] warning: skipping node %s because v.instance is None" % str(node_label))
            continue

        inst_name = v.instance.name

        if inst_name not in node_coord_map:
            skipped_missing_coord += 1
            log("[visualization.py] warning: instance %s not found in node_coord_map" % str(inst_name))
            continue

        if node_label not in node_coord_map[inst_name]:
            skipped_missing_coord += 1
            log("[visualization.py] warning: node %s not found in node_coord_map[%s]" % (str(node_label),
                                                                                         str(inst_name)))
            continue

        coords = node_coord_map[inst_name][node_label]
        x = coords[0]
        y = coords[1]
        z = coords[2]

        data = list(v.data)
        while len(data) < 3:
            data.append(0.0)

        u1 = data[0]
        u2 = data[1]
        u3 = data[2]
        mag = math.sqrt(u1 * u1 + u2 * u2 + u3 * u3)

        if mag > max_mag:
            max_mag = mag
            max_node = (inst_name, node_label, u1, u2, u3, mag)

        writer.writerow([
            inst_name,
            node_label,
            x, y, z,
            u1, u2, u3, mag
        ])
        written_count += 1

    f.close()
    log("[visualization.py] CSV written successfully")
    log("[visualization.py] rows written = %d" % written_count)
    log("[visualization.py] skipped because instance was None = %d" % skipped_none_instance)
    log("[visualization.py] skipped because coordinates were missing = %d" % skipped_missing_coord)
    log("[visualization.py] max displacement magnitude = %s" % max_mag)
    log("[visualization.py] node with max displacement = %s" % str(max_node))
    log("[visualization.py] csv path = %s" % disp_csv)

    df = open(done_file, "w")
    df.write("Visualization completed successfully.\n")
    df.write("ODB: %s\n" % odb_path)
    df.write("CSV: %s\n" % disp_csv)
    df.write("Rows written: %d\n" % written_count)
    df.write("Skipped because instance was None: %d\n" % skipped_none_instance)
    df.write("Skipped because coordinates were missing: %d\n" % skipped_missing_coord)
    df.write("Max magnitude: %s\n" % max_mag)
    df.write("Max node: %s\n" % str(max_node))
    df.close()

    log("[visualization.py] done file written")
    log("[visualization.py] Abaqus Viewer remains open")

except Exception as e:
    ef = open(error_file, "w")
    ef.write("Visualization failed.\n\n")
    ef.write(str(e) + "\n\n")
    ef.write(traceback.format_exc())
    ef.close()

    log("[visualization.py] ERROR occurred")
    log(str(e))
    log(traceback.format_exc())
    raise