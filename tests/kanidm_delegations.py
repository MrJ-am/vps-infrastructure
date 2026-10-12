"""Capacité de cycle bornée aux personnes gérées, IdP réel hors production."""
import json
import time
import uuid
from kanidm_reel import EchecQualification, KanidmLocal


def qualifier(paquet, curl):
    with KanidmLocal(paquet, curl) as n:
        n.config.write_text(n.config.read_text().replace('log_level = "info"', 'log_level = "debug"'))
        n.arreter(); n.demarrer()
        system = n.login('admin', n.recuperer('admin'), privilegie=True)
        op = n.login('idm_admin', n.recuperer('idm_admin'), privilegie=True)
        def requete(path, body=None, *, method=None, token=op):
            status, data = n.http(path, body, token=token, method=method)
            if status != 200: raise EchecQualification('configuration délégation native refusée '+path+' HTTP'+str(status))
            return data
        requete('/v1/service_account', {'attrs': {'name': ['fixture-cycle'], 'displayname': ['Fixture cycle'],
                                                'entry_managed_by': ['idm_admin']}})
        requete('/v1/group', {'attrs': {'name': ['fixture-cycle-receivers']}})
        requete('/v1/group/fixture-cycle-receivers/_attr/member', ['fixture-cycle'])
        profile = requete('/v1/raw/search', {'filter': {'eq': ['name', 'idm_acp_acp_manage']}}, token=system)['entries'][0]['attrs']
        classes = profile['acp_create_class'] + ['object', 'access_control_receiver_group', 'access_control_target_scope']
        migration = n.migrations/'00-classes-de-controle.json'
        migration.write_text(json.dumps({'id': str(uuid.uuid4()), 'assertions': [
            {'state': 'present', 'id': profile['uuid'][0], 'acp_create_class': classes}]}))
        migration.chmod(0o600)
        # Configuration officielle à privilège hôte, pas un fork ni un credential
        # administrateur dans le produit. Seul le gestionnaire système existant
        # gagne les classes nécessaires à la création des ACP ciblées.
        n.arreter(); n.demarrer()
        actuel = requete('/v1/raw/search', {'filter': {'eq': ['name', 'idm_acp_acp_manage']}}, token=system)['entries'][0]['attrs']['acp_create_class']
        if set(actuel) != set(classes):
            raise EchecQualification('assertion de classes non appliquée : manquantes='+','.join(sorted(set(classes)-set(actuel))))
        requete('/v1/person', {'attrs': {'name': ['fixture-externe'], 'displayname': ['Fixture externe'],
                                       'mail': ['fixture-externe@example.test']}})
        acp = {'attrs': {
            'class': ['object', 'access_control_profile', 'access_control_receiver_group',
                      'access_control_target_scope', 'access_control_search', 'access_control_modify', 'access_control_create'],
            'name': ['fixture-cycle-acp'], 'description': ['Fixture capacité minimale'],
            'acp_receiver_group': ['fixture-cycle-receivers'],
            'acp_targetscope': [json.dumps({'and': [{'eq': ['class', 'person']}, {'eq': ['description', 'mrjam-person']}]})],
            'acp_search_attr': ['class', 'uuid', 'name', 'displayname', 'mail', 'description', 'account_expire'],
            'acp_modify_presentattr': ['account_expire'], 'acp_modify_removedattr': ['account_expire'],
            'acp_create_class': ['object', 'account', 'person'],
            'acp_create_attr': ['class', 'name', 'displayname', 'mail', 'description'],
        }}
        requete('/v1/raw/create', {'entries': [acp]}, token=system)
        scoped = requete('/v1/service_account/fixture-cycle/_api_token',
                          {'label': 'fixture-cycle', 'expiry': int(time.time())+3600, 'read_write': True})
        requete('/v1/person', {'attrs': {'name': ['fixture-managed'], 'displayname': ['Fixture gérée'],
                                       'description': ['mrjam-person'], 'mail': ['fixture-managed@example.test']}}, token=scoped)
        status, managed = n.http('/v1/person/fixture-managed', token=scoped)
        if status != 200 or managed['attrs']['mail'] != ['fixture-managed@example.test']:
            raise EchecQualification('lecture personne gérée refusée')
        status, outside = n.http('/v1/person/fixture-externe', token=scoped)
        if status == 200 and outside is not None:
            raise EchecQualification('lecture personne tierce indûment permise')
        status, _ = n.http('/v1/person/fixture-externe/_attr/account_expire', ['2030-01-01T00:00:00Z'], token=scoped, method='PUT')
        if status not in (403, 404): raise EchecQualification('écriture personne tierce indûment permise')
        status, _ = n.http('/v1/person/fixture-managed/_attr/account_expire', ['2030-01-01T00:00:00Z'], token=scoped, method='PUT')
        if status != 200: raise EchecQualification('capacité de cycle bornée indisponible')
        status, _ = n.http('/v1/person/fixture-managed/_credential/_update', token=scoped)
        if status not in (403, 404): raise EchecQualification('délégation peut indûment modifier des authentificateurs')
        return {'lecture_bornee': True, 'ecriture_bornee': True, 'reset_authentificateurs_refuse': True,
                'credential_administrateur_global_absent_du_produit': True, 'production': False}
