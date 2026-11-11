"""Read a solved Aspen Plus document through COM into the processData dictionary used by the cost model.

Requires Aspen Plus V14 and pywin32 (Windows).  Reads every block (temperature, pressure, duty, connections, type),
every stream (bulk flows, density, pH from the PHSET property set) and the MIXED / CISOLID component flows, then
classifies feed and product streams from the block connections and reads the design-spec results.
"""
import pandas as pd


def _safe_get(node):
    """Safely get value from Aspen tree node; return None on failure."""
    try:
        return node.Value
    except Exception:
        return None


def get_components(h):
    r"""
    Discover all component IDs from Aspen Specifications\Input\ANAME.

    Returns
    -------
    comp_list : list of str – component IDs (e.g., WATER, HCL, FE2O3, ...)
    comp_types : dict – {comp_id: 'CONV' or 'SOLID'}
    """
    tree = h.Tree
    comp_list = []
    comp_types = {}

    # Read from Input\ANAME (works for this simulation)
    aname_node = tree.FindNode(r'\Data\Components\Specifications\Input\ANAME')
    type_node = tree.FindNode(r'\Data\Components\Specifications\Input\TYPE')

    if aname_node is not None:
        n = aname_node.Elements.Count
        for i in range(n):
            comp_id = aname_node.Elements.ItemName(i)
            comp_list.append(comp_id)
            # Get type (CONV or SOLID)
            if type_node is not None:
                try:
                    comp_types[comp_id] = type_node.FindNode(comp_id).Value
                except Exception:
                    comp_types[comp_id] = 'CONV'
    else:
        # Fallback: try Selection path
        sel_node = tree.FindNode(r'\Data\Components\Specifications\Selection')
        if sel_node is not None:
            n = sel_node.Elements.Count
            for i in range(n):
                comp_list.append(sel_node.Elements.ItemName(i))

    return comp_list, comp_types


def get_stream_component_flows(h, stream_name, components, substream='MIXED'):
    """
    Get component-level mass and mole flows for a given stream and substream.

    Returns
    -------
    mass_flows : dict  {comp_name: mass_flow_kg_hr}
    mole_flows : dict  {comp_name: mole_flow_kmol_hr}
    """
    tree = h.Tree
    mass_flows = {}
    mole_flows = {}

    for comp in components:
        # Mass flow (kg/hr)
        try:
            val = tree.FindNode(
                fr'\Data\Streams\{stream_name}\Output\MASSFLOW\{substream}\{comp}'
            ).Value
            mass_flows[comp] = val if val is not None else 0.0
        except Exception:
            mass_flows[comp] = 0.0

        # Mole flow (kmol/hr)
        try:
            val = tree.FindNode(
                fr'\Data\Streams\{stream_name}\Output\MOLEFLOW\{substream}\{comp}'
            ).Value
            mole_flows[comp] = val if val is not None else 0.0
        except Exception:
            mole_flows[comp] = 0.0

    return mass_flows, mole_flows


def access_data(processData, h):
    """
    Read all block/stream data from Aspen Plus COM handle for Ash extraction process.
    Includes component-level composition for every stream.

    Parameters
    ----------
    processData : dict
    h           : COM object - Aspen Plus Document handle

    Returns
    -------
    processData : dict - populated with Units, Streams, Components,
                         StreamCompositions, Input, Output.
    """
    tree = h.Tree

    # =================================================================
    # Discover Components
    # =================================================================
    components, comp_types = get_components(h)
    processData['Components'] = components
    processData['ComponentTypes'] = comp_types
    conv_comps = [c for c in components if comp_types.get(c) == 'CONV']
    solid_comps = [c for c in components if comp_types.get(c) == 'SOLID']

    # =================================================================
    # Units (Blocks)
    # =================================================================
    blockAddr = tree.FindNode(r'\Data\Blocks')
    unitCount = blockAddr.Elements.Count

    units_data = []
    for i in range(unitCount):
        name = blockAddr.Elements.ItemName(i)
        row = {'NAME': name}

        # Temperature [C]
        try:
            row['TEMPERATURE'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\B_TEMP').Value
        except Exception:
            row['TEMPERATURE'] = None

        # Pressure [bar]
        try:
            row['PRESSURE'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\B_PRES').Value
        except Exception:
            try:
                row['PRESSURE'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\HOTINP').Value
            except Exception:
                row['PRESSURE'] = None

        # Heat duty [cal/s]
        try:
            row['HEATDUTY'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\QCALC').Value
        except Exception:
            try:
                row['HEATDUTY'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\HX_DUTY').Value
            except Exception:
                row['HEATDUTY'] = None

        # Condenser duty [cal/s]
        try:
            row['CONDDUTY'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\COND_DUTY').Value
        except Exception:
            row['CONDDUTY'] = None

        # Top temperature [C]
        try:
            row['Top_Temperature'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\B_TEMP\1').Value
        except Exception:
            row['Top_Temperature'] = None

        # Reboiler duty [cal/s]
        try:
            row['REBDUTY'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\REB_DUTY').Value
        except Exception:
            row['REBDUTY'] = None

        # Work [kW]
        try:
            row['WORK'] = tree.FindNode(fr'\Data\Blocks\{name}\Output\WNET').Value
        except Exception:
            row['WORK'] = None

        # Balance flows
        for key, path in [
            ('MOLEFLOW_IN', 'BAL_MOLI_TFL'), ('MOLEFLOW_OUT', 'BAL_MOLO_TFL'),
            ('MASSFLOW_IN', 'BAL_MASI_TFL'), ('MASSFLOW_OUT', 'BAL_MASO_TFL'),
            ('ENTH_IN', 'TOT_ENTH_ABS'), ('ENTH_OUT', 'BAL_ENTH_OUT'),
        ]:
            try:
                row[key] = tree.FindNode(fr'\Data\Blocks\{name}\Output\{path}').Value
            except Exception:
                row[key] = None

        # Connections
        connNode = tree.FindNode(fr'\Data\Blocks\{name}\Connections')
        conn = {}
        if connNode is not None:
            numCon = connNode.Elements.Count
            for j in range(numCon):
                cname = connNode.Elements.ItemName(j)
                cval = tree.FindNode(fr'\Data\Blocks\{name}\Connections\{cname}').Value
                conn[cname] = cval
        row['CONNECTION'] = conn

        # Block type
        row['TYPE'] = blockAddr.FindNode(name).AttributeValue(6)

        units_data.append(row)

    processData['Units'] = pd.DataFrame(units_data)

    # =================================================================
    # Streams (bulk properties + component compositions)
    # =================================================================
    allStreams = tree.FindNode(r'\Data\Streams')
    numStreams = allStreams.Elements.Count

    streams_data = []
    stream_compositions = {}

    for i in range(numStreams):
        sname = allStreams.Elements.ItemName(i)
        row = {'NAME': sname}

        # Temperature [C] - try MIXED first, then CISOLID
        row['TEMPERATURE'] = None
        for sub in ['MIXED', 'CISOLID']:
            if row['TEMPERATURE'] is None:
                try:
                    row['TEMPERATURE'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\TEMP_OUT\{sub}').Value
                except Exception:
                    pass

        # Pressure [bar]
        row['PRESSURE'] = None
        for sub in ['MIXED', 'CISOLID']:
            if row['PRESSURE'] is None:
                try:
                    row['PRESSURE'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\PRES_OUT\{sub}').Value
                except Exception:
                    pass

        # MIXED substream flows
        try:
            row['MASSFLOW_MIXED'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\MASSFLMX\MIXED').Value
        except Exception:
            row['MASSFLOW_MIXED'] = 0.0
        try:
            row['MOLEFLOW_MIXED'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\MOLEFLMX\MIXED').Value
        except Exception:
            row['MOLEFLOW_MIXED'] = 0.0

        # CISOLID substream flows
        try:
            row['MASSFLOW_CISOLID'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\MASSFLMX\CISOLID').Value
        except Exception:
            row['MASSFLOW_CISOLID'] = 0.0
        try:
            row['MOLEFLOW_CISOLID'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\MOLEFLMX\CISOLID').Value
        except Exception:
            row['MOLEFLOW_CISOLID'] = 0.0

        # Total = MIXED + CISOLID
        mf_mixed = row['MASSFLOW_MIXED'] or 0.0
        mf_cisolid = row['MASSFLOW_CISOLID'] or 0.0
        row['MASSFLOW_TOTAL'] = mf_mixed + mf_cisolid

        mol_mixed = row['MOLEFLOW_MIXED'] or 0.0
        mol_cisolid = row['MOLEFLOW_CISOLID'] or 0.0
        row['MOLEFLOW_TOTAL'] = mol_mixed + mol_cisolid

        # Volume flow & density (MIXED)
        try:
            row['VOLFLOW'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\VOLFLMX\MIXED').Value
        except Exception:
            row['VOLFLOW'] = None
        try:
            row['DENSITY'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\RHOMX_MASS\MIXED').Value
        except Exception:
            row['DENSITY'] = None

        # Enthalpy
        try:
            row['ENTHALPY'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\HMX\MIXED').Value
        except Exception:
            row['ENTHALPY'] = None

        # Stream phase type
        try:
            row['COMPTYPE'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\COMPTYPE').Value
        except Exception:
            row['COMPTYPE'] = None

        # pH from user-defined Property Set "PHSET"
        row['PH'] = None
        for ph_path in [
            # User Property Set "PHSET"
            fr'\Data\Streams\{sname}\Output\STR_MAIN\PROPS\PHSET\MIXED',
            fr'\Data\Streams\{sname}\Output\PROPS\PHSET\MIXED',
            fr'\Data\Streams\{sname}\Output\PROP_SET\PHSET\MIXED',
            fr'\Data\Streams\{sname}\Output\PHSET\MIXED',
            # Fallback: built-in pH paths
            fr'\Data\Streams\{sname}\Output\PHMX\MIXED',
            fr'\Data\Streams\{sname}\Output\PH\MIXED',
        ]:
            try:
                node = tree.FindNode(ph_path)
                if node is not None:
                    val = node.Value
                    if val is not None:
                        row['PH'] = val
                        break
                    # Maybe sub-elements (PHSET may have multiple properties)
                    for k in range(node.Elements.Count):
                        sk = node.Elements.ItemName(k)
                        if 'PH' in sk.upper():
                            sv = node.Elements.Item(k).Value
                            if sv is not None:
                                row['PH'] = sv
                                break
                    if row['PH'] is not None:
                        break
            except Exception:
                pass

        # Heat/energy streams
        row['DUTY'] = None
        row['T_begin'] = None
        row['T_end'] = None
        if row['TEMPERATURE'] is None:
            try:
                row['DUTY'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\QCALC').Value
                row['T_begin'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\TBEGIN').Value
                row['T_end'] = tree.FindNode(fr'\Data\Streams\{sname}\Output\TEND').Value
            except Exception:
                pass

        streams_data.append(row)

        # ------ Component-level compositions ------
        comp_data = {}
        for substream in ['MIXED', 'CISOLID']:
            mass_flows, mole_flows = get_stream_component_flows(h, sname, components, substream)
            total_mass = sum(abs(v) for v in mass_flows.values())
            if total_mass > 1e-10:
                comp_data[substream] = {
                    'mass_flow': mass_flows,
                    'mole_flow': mole_flows,
                }
        stream_compositions[sname] = comp_data

    processData['Streams'] = pd.DataFrame(streams_data)
    processData['StreamCompositions'] = stream_compositions

    # =================================================================
    # Build component flow DataFrames for easy viewing
    # =================================================================
    mass_flow_table = []
    for sname in [s['NAME'] for s in streams_data]:
        row = {'Stream': sname}
        comp_data = stream_compositions.get(sname, {})
        for sub in ['MIXED', 'CISOLID']:
            if sub in comp_data:
                suffix = '' if sub == 'MIXED' else f'_{sub}'
                for comp, val in comp_data[sub]['mass_flow'].items():
                    row[f'{comp}{suffix}'] = val
        mass_flow_table.append(row)
    processData['MassFlowTable'] = pd.DataFrame(mass_flow_table).fillna(0)

    mole_flow_table = []
    for sname in [s['NAME'] for s in streams_data]:
        row = {'Stream': sname}
        comp_data = stream_compositions.get(sname, {})
        for sub in ['MIXED', 'CISOLID']:
            if sub in comp_data:
                suffix = '' if sub == 'MIXED' else f'_{sub}'
                for comp, val in comp_data[sub]['mole_flow'].items():
                    row[f'{comp}{suffix}'] = val
        mole_flow_table.append(row)
    processData['MoleFlowTable'] = pd.DataFrame(mole_flow_table).fillna(0)

    # =================================================================
    # Classify Input / Output streams
    # =================================================================
    processData['Input'] = {}
    processData['Output'] = {}

    all_block_outputs = set()
    all_block_inputs = set()
    for _, urow in processData['Units'].iterrows():
        conn = urow.get('CONNECTION', {})
        if isinstance(conn, dict):
            for sname_c, port in conn.items():
                if '(IN)' in str(port):
                    all_block_inputs.add(sname_c)
                elif '(OUT)' in str(port):
                    all_block_outputs.add(sname_c)

    feed_streams = all_block_inputs - all_block_outputs
    product_streams = all_block_outputs - all_block_inputs

    for sname in feed_streams:
        srow = processData['Streams'][processData['Streams']['NAME'] == sname]
        if not srow.empty:
            s = srow.iloc[0]
            processData['Input'][sname] = {
                'Massflow_Total': s['MASSFLOW_TOTAL'],
                'Massflow_Mixed': s['MASSFLOW_MIXED'],
                'Massflow_CISolid': s['MASSFLOW_CISOLID'],
                'Moleflow_Total': s['MOLEFLOW_TOTAL'],
                'Temperature': s['TEMPERATURE'],
                'Pressure': s['PRESSURE'],
            }

    for sname in product_streams:
        srow = processData['Streams'][processData['Streams']['NAME'] == sname]
        if not srow.empty:
            s = srow.iloc[0]
            processData['Output'][sname] = {
                'Massflow_Total': s['MASSFLOW_TOTAL'],
                'Massflow_Mixed': s['MASSFLOW_MIXED'],
                'Massflow_CISolid': s['MASSFLOW_CISOLID'],
                'Moleflow_Total': s['MOLEFLOW_TOTAL'],
                'Temperature': s['TEMPERATURE'],
                'Pressure': s['PRESSURE'],
            }

    processData['FeedStreams'] = sorted(feed_streams)
    processData['ProductStreams'] = sorted(product_streams)

    # =================================================================
    # Design Specs — read pH targets and final values
    # =================================================================
    design_specs = {}
    ds_node = tree.FindNode(r'\Data\Flowsheeting Options\Design-Spec')
    if ds_node is not None:
        for i in range(ds_node.Elements.Count):
            ds_name = ds_node.Elements.ItemName(i)
            ds_info = {'name': ds_name}
            # Read FINAL_VAL (converged values: manipulated var + spec var)
            for key in ['FINAL_VAL', 'INIT_VAL', 'VARID', 'VAR_UNIT', 'BLKSTAT']:
                try:
                    node = tree.FindNode(
                        fr'\Data\Flowsheeting Options\Design-Spec\{ds_name}\Output\{key}')
                    if node is not None:
                        vals = []
                        try:
                            for j in range(node.Elements.Count):
                                vals.append(node.Elements.Item(j).Value)
                        except Exception:
                            vals = [node.Value]
                        ds_info[key] = vals
                except Exception:
                    pass
            design_specs[ds_name] = ds_info

    processData['DesignSpecs'] = design_specs
    return processData
