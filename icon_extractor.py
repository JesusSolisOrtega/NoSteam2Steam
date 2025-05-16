import logging
import pefile
import os
import struct
from collections import OrderedDict

logger = logging.getLogger("no_steam_to_steam")

def extract_icon(exe_path, output_path):
    if os.path.exists(output_path):
        logger.info(f"El archivo {output_path} ya existe. Saltando extracción.")
        return True
    
    if not os.path.exists(exe_path):
        logger.error(f"Error: No se encontró el archivo {exe_path}")
        return False

    success, icon_data = standart_extraction_method(exe_path)
    if success:
        with open(output_path, "wb") as f:
            f.write(icon_data)
        logger.info(f"Icono extraído correctamente (método estándar): {output_path}")
        return True
    
    logger.info("Fallo en método estándar, intentando método flexible completo...")
    success, icon_data = flexible_extraction_method(exe_path)
    if success:
        with open(output_path, "wb") as f:
            f.write(icon_data)
        logger.info(f"Icono extraído correctamente (método flexible): {output_path}")
        return True
    
    logger.error("No se pudo extraer el icono con ningún método.")
    return False

def standart_extraction_method(exe_path):
    try:
        pe = pefile.PE(exe_path, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
        
        group_icon_data = None
        icon_data = OrderedDict()
        mapped_data = None

        if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
            mapped_data = pe.get_memory_mapped_image()

            # Buscar grupo de iconos
            for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
                if entry.id == pefile.RESOURCE_TYPE['RT_GROUP_ICON']:
                    for res in entry.directory.entries:
                        for icon_entry in res.directory.entries:
                            data_rva = icon_entry.data.struct.OffsetToData
                            size = icon_entry.data.struct.Size
                            group_icon_data = mapped_data[data_rva:data_rva+size]
                            break
                    break

            if group_icon_data:
                for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
                    if entry.id == pefile.RESOURCE_TYPE['RT_ICON']:
                        for res in entry.directory.entries:
                            for icon_entry in res.directory.entries:
                                data_rva = icon_entry.data.struct.OffsetToData
                                size = icon_entry.data.struct.Size
                                icon_data[res.id] = mapped_data[data_rva:data_rva+size]

        if group_icon_data is None:
            return False, None

        num_icons = struct.unpack("<H", group_icon_data[4:6])[0]
        icon_entries = []
        size_mismatch = False
        
        for i in range(num_icons):
            offset = 6 + i * 14
            if offset + 14 > len(group_icon_data):
                continue
            
            data = group_icon_data[offset:offset+14]
            
            try:
                width, height, _, planes, bit_count, bytes_in_res, icon_id = struct.unpack("<BBBxHHIH", data)
                width = 256 if width == 0 else width
                height = 256 if height == 0 else height
                
                if icon_id in icon_data:
                    actual_size = len(icon_data[icon_id])
                    if actual_size != bytes_in_res:
                        logger.warning(f"Advertencia: Tamaño de icono {icon_id} no coincide ({actual_size} vs {bytes_in_res})")
                        size_mismatch = True
                        continue
                    
                    icon_entries.append({
                        "width": width,
                        "height": height,
                        "bit_count": bit_count,
                        "planes": planes,
                        "data": icon_data[icon_id]
                    })
            except:
                continue

        if not icon_entries:
            return False, None

        ico_data = build_complete_ico(icon_entries)
        return True, ico_data

    except Exception as e:
        logger.error(f"Error en método estándar: {str(e)}")
        return False, None
    finally:
        if 'pe' in locals():
            pe.close()

def flexible_extraction_method(exe_path):
    try:
        pe = pefile.PE(exe_path, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
        
        icon_resources = []
        
        if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
            mapped_data = pe.get_memory_mapped_image()
            
            for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
                if entry.id in (pefile.RESOURCE_TYPE['RT_GROUP_ICON'], 3, 14): 
                    for res in entry.directory.entries:
                        for item in res.directory.entries:
                            try:
                                data_rva = item.data.struct.OffsetToData
                                size = item.data.struct.Size
                                if data_rva + size > len(mapped_data):
                                    continue
                                icon_resources.append({
                                    'type': entry.id,
                                    'id': res.id,
                                    'data': mapped_data[data_rva:data_rva+size]
                                })
                            except:
                                continue

        if not icon_resources:
            for section in pe.sections:
                if b'.rsrc' in section.Name:
                    data = section.get_data()
                    patterns = [b'\x00\x00\x01\x00', b'\x00\x00\x02\x00']
                    for pattern in patterns:
                        pos = data.find(pattern)
                        if pos != -1:
                            icon_resources.append({
                                'type': 3,  # RT_ICON
                                'id': len(icon_resources) + 1,
                                'data': data[pos:]
                            })

        group_icons = [r for r in icon_resources if r['type'] == pefile.RESOURCE_TYPE['RT_GROUP_ICON'] or r['type'] == 14]
        single_icons = {r['id']: r['data'] for r in icon_resources if r['type'] == pefile.RESOURCE_TYPE['RT_ICON'] or r['type'] == 3}
        
        if not group_icons and not single_icons:
            return False, None
        
        ico_data = None
        if group_icons:
            try:
                group_data = group_icons[0]['data']
                num_icons = struct.unpack("<H", group_data[4:6])[0] if len(group_data) >= 6 else 0
                icon_entries = []
                
                for i in range(num_icons):
                    offset = 6 + i * 14
                    if offset + 14 > len(group_data):
                        continue
                    
                    width, height, _, planes, bit_count, size, icon_id = struct.unpack("<BBBxHHIH", group_data[offset:offset+14])
                    width = 256 if width == 0 else width
                    height = 256 if height == 0 else height
                    
                    if icon_id in single_icons:
                        actual_size = len(single_icons[icon_id])
                        if actual_size != size:
                            logger.warning(f"Advertencia (flexible): Tamaño de icono {icon_id} no coincide ({actual_size} vs {size})")
                            continue
                        
                        icon_entries.append({
                            'width': width,
                            'height': height,
                            'bit_count': bit_count,
                            'planes': planes,
                            'data': single_icons[icon_id]
                        })

                if icon_entries:
                    ico_data = build_complete_ico(icon_entries)
            except Exception as e:
                logger.error(f"Error al procesar grupo de iconos (flexible): {e}")

        if not ico_data and single_icons:
            icon_entries = []
            for icon_id, data in single_icons.items():
                try:
                    if len(data) >= 40:
                        width = data[0] or 256
                        height = data[1] or 256
                        bit_count = struct.unpack("<H", data[6:8])[0]
                        icon_entries.append({
                            'width': width,
                            'height': height,
                            'bit_count': bit_count,
                            'planes': 1,
                            'data': data
                        })
                except:
                    continue
            
            if icon_entries:
                ico_data = build_complete_ico(icon_entries)

        if ico_data:
            return True, ico_data
        return False, None

    except Exception as e:
        logger.error(f"Error en método flexible: {str(e)}")
        return False, None
    finally:
        if 'pe' in locals():
            pe.close()

def build_complete_ico(icon_entries):
    icon_entries.sort(key=lambda x: (-x['width'], -x['height'], -x['bit_count']))
    
    header = struct.pack("<HHH", 0, 1, len(icon_entries))
    entries = b""
    data = b""
    offset = 6 + 16 * len(icon_entries)
    
    for icon in icon_entries:
        width = 0 if icon['width'] >= 256 else icon['width']
        height = 0 if icon['height'] >= 256 else icon['height']
        
        entries += struct.pack("<BBBxHHII", 
                                width, height, 0, icon['planes'], icon['bit_count'], 
                                len(icon['data']), offset)
        data += icon['data']
        offset += len(icon['data'])
    
    return header + entries + data


