"""Accepter seulement la même boucle IPv4, y compris sa notation IPv6 mappée."""
import ipaddress
import re


def verifier(texte):
    lignes=texte.splitlines()
    if len(lignes)!=1: return False
    champs=lignes[0].split()
    if len(champs)<5 or champs[0]!='LISTEN': return False
    adresse=champs[3]
    if "%" in adresse: return False
    m=re.fullmatch(r'(?:\[([^\[\]]+)\]|([^:\[\]]+)):8085',adresse)
    if not m: return False
    try:
        ip=ipaddress.ip_address(m[1] or m[2])
    except ValueError: return False
    if isinstance(ip,ipaddress.IPv6Address): ip=ip.ipv4_mapped
    return ip==ipaddress.IPv4Address('127.0.0.1')
