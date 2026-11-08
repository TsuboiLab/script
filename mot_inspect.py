import sys, io, hashlib, inspect
sys.path.insert(0, r'C:\Users\domepc6-tsuboi\work\mot_analysis_deps')
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_MODE_64
from elftools.dwarf.dwarfinfo import DWARFInfo, DwarfConfig, DebugSectionDescriptor
p=pefile.PE(r'C:\Users\domepc6-tsuboi\Documents\nishimura\Master\Master2018.exe')
base=p.OPTIONAL_HEADER.ImageBase
if len(sys.argv)>1 and sys.argv[1]=='refs':
    import struct
    for addr in [0x7cd63c,0x7cd682,0x7cd630,0x7cd687,0x7cd68d]:
        print(hex(addr),p.get_data(addr-base,25))
    print('table', [hex(0x45e550+x) for x in struct.unpack('<9i',p.get_data(0x45e550-base,36))])
    md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True; md.skipdata=True
    for s in p.sections:
        if s.Characteristics & 0x20:
            for x in md.disasm(s.get_data(),base+s.VirtualAddress):
                if not x.id: continue
                for op in x.operands:
                    if op.type==3 and x.reg_name(op.mem.base)=='rip':
                        target=x.address+x.size+op.mem.disp
                        if target in [0x16cb36c,0x16cb628,0x16cb624,0x16cb66a,0x16cb66b]:
                            print(hex(x.address),hex(target),x.mnemonic,x.op_str)
elif len(sys.argv)>1:
    addr=int(sys.argv[1],16); size=int(sys.argv[2],16)
    for x in Cs(CS_ARCH_X86,CS_MODE_64 if p.FILE_HEADER.Machine==0x8664 else CS_MODE_32).disasm(p.get_data(addr-base,size),addr):
        print(hex(x.address),x.mnemonic,x.op_str)
else:
    print(hashlib.sha256(p.__data__).hexdigest(),hex(base))
    sections={s.Name.decode().strip('\0'):s for s in p.sections}
    # PE long section names refer into the COFF string table.
    off=p.FILE_HEADER.PointerToSymbolTable+p.FILE_HEADER.NumberOfSymbols*18
    for name,s in list(sections.items()):
        if name.startswith('/'):
            i=off+int(name[1:]); real=p.__data__[i:].split(b'\0',1)[0].decode(); sections[real]=s
    args={}
    for key in inspect.signature(DWARFInfo).parameters:
        if key=='config': args[key]=DwarfConfig(little_endian=True,machine_arch='x86',default_address_size=4)
        else:
            s=sections.get('.'+key.removesuffix('_sec'))
            args[key]=DebugSectionDescriptor(io.BytesIO(s.get_data()),s.Name.decode(),0,len(s.get_data()),s.VirtualAddress) if s else None
    dwarf=DWARFInfo(**args)
    for cu in dwarf.iter_CUs():
        for die in cu.iter_DIEs():
            a=die.attributes; name=a.get('DW_AT_name')
            if name and any(t in str(name.value).lower() for t in ['guide','makestatus','telstat','sidereal','track','timer','buttonstop']):
                print(die.tag,{k:v.value for k,v in a.items()})
