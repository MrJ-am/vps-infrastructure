"""Preuve limitée aux notes des sessions du sujet initial exact, pas aux contenus."""
import json


def verifier_notes(data, executions, maintenant):
    if not isinstance(data,dict) or data.get('authMethod')!='openid-connect':return False
    notes=data.get('notes')
    if not isinstance(notes,dict):return False
    try:
        date=int(notes.get('AUTH_TIME','-1'))
        completes=json.loads(notes.get('authenticators-completed','{}'))
    except (TypeError,ValueError):return False
    if not isinstance(completes,dict) or not 0<=maintenant-date<=300:return False
    for methode in ('pwd','otp'):
        ids=executions.get(methode,())
        if len(ids)!=1:return False
        temps=completes.get(ids[0])
        if type(temps) is not int or not 0<=maintenant-temps<=300:return False
    return True
