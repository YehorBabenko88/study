"""Export actual glTF 2.0 triangle mesh from spectral samples and a parametric shape.

The user's arbitrary noun is descriptive metadata; no unverified text-to-3D model.
"""
import base64
import json
import math
import struct

SHAPES={"sphere","flower","star","vase","bell"}

def mesh(spectrum,shape="sphere",strength=.25,label="",profile=None):
    if shape not in SHAPES:raise ValueError("Unsupported shape preset")
    if not isinstance(label,str) or len(label)>120:raise ValueError("Invalid label")
    if not isinstance(strength,(int,float)) or not math.isfinite(strength) or not 0<=strength<=1:
        raise ValueError("Invalid strength")
    if not isinstance(spectrum,list) or not 1<=len(spectrum)<=280:
        raise ValueError("Invalid spectrum")
    if any(not isinstance(row,list) or not 1<=len(row)<=128 or
           any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in row)
           for row in spectrum):
        raise ValueError("Invalid spectrum")
    if profile is not None and (not isinstance(profile,list) or len(profile)!=9 or
        any(not isinstance(v,(int,float)) or not math.isfinite(v) or not .2<=v<=2 for v in profile)):
        raise ValueError("Profile must have 9 finite radii")
    lat=32;lon=64;vertices=[];indices=[]
    for i in range(lat+1):
        phi=math.pi*i/lat
        for j in range(lon+1):
            theta=2*math.pi*j/lon
            v=spectrum[min(len(spectrum)-1,int(j/lon*len(spectrum)))]
            e=v[min(len(v)-1,int(i/lat*len(v)))]
            r=1+strength*.4*e
            if shape=="flower":r*=1+.15*math.cos(8*theta)
            elif shape=="star":r*=1+.2*math.cos(5*theta)
            elif shape=="vase":r*=.8+.3*math.sin(phi)
            elif shape=="bell":r*=.75+.3*math.cos(phi)
            if profile:
                k=min(7,int(i/lat*8));f=i/lat*8-k
                r*=profile[k]*(1-f)+profile[k+1]*f
            vertices.extend([r*math.sin(phi)*math.cos(theta),
                             r*math.cos(phi),r*math.sin(phi)*math.sin(theta)])
    for i in range(lat):
        for j in range(lon):
            a=i*(lon+1)+j;b=a+lon+1
            indices.extend([a,b,a+1,a+1,b,b+1])
    positions=struct.pack("<"+"f"*len(vertices),*vertices)
    faces=struct.pack("<"+"I"*len(indices),*indices)
    blob=positions+faces
    lo=[min(vertices[k::3]) for k in range(3)]
    hi=[max(vertices[k::3]) for k in range(3)]
    gltf={"asset":{"version":"2.0","generator":"Study PhonoVision"},
          "scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0,"name":label or shape}],
          "meshes":[{"primitives":[{"attributes":{"POSITION":0},"indices":1,"material":0}]}],
          "materials":[{"pbrMetallicRoughness":{"baseColorFactor":[.26,.65,.85,1],"metallicFactor":0,"roughnessFactor":.6},"doubleSided":True}],
          "buffers":[{"byteLength":len(blob),"uri":"data:application/octet-stream;base64,"+base64.b64encode(blob).decode("ascii")}],
          "bufferViews":[{"buffer":0,"byteOffset":0,"byteLength":len(positions),"target":34962},
                         {"buffer":0,"byteOffset":len(positions),"byteLength":len(faces),"target":34963}],
          "accessors":[{"bufferView":0,"componentType":5126,"count":len(vertices)//3,"type":"VEC3","min":lo,"max":hi},
                       {"bufferView":1,"componentType":5125,"count":len(indices),"type":"SCALAR"}],
          "extras":{"acoustic_mapping":"normalized_magnitude_to_radial_displacement",
                    "shape_preset":shape,"user_label":label,
                    "not_an_invertible_audio_representation":True}}
    return gltf
