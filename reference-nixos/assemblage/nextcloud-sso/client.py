"""One explicitly bound Nextcloud client; no personal credential recovery."""
import importlib.util,json,pathlib,re,tempfile,urllib.parse
CLIENT='mrjam-nextcloud'
GROUP='mrjam-nextcloud-owner'
CALLBACK='https://cloud.mrj.am/index.php/apps/user_oidc/code'
DISCOVERY='https://log.mrj.am/oauth2/openid/'+CLIENT+'/.well-known/openid-configuration'

def configure(api, token, uid, expected_subject, callback=CALLBACK):
    attrs=api.http('/v1/group/mrjam-proprietaire-policy',token=token)['attrs']
    members=attrs.get('member',[])
    if len(members)!=1:raise RuntimeError('Ambiguous native owner group')
    person=api.http('/v1/person/'+members[0].split('@')[0],token=token)['attrs']
    subject=person['uuid'][0]
    if subject!=expected_subject:raise RuntimeError('Native owner binding changed')
    groups=api.http('/v1/group',token=token)
    if not any(g['attrs'].get('name')==[GROUP] for g in groups):
        api.http('/v1/group',{'attrs':{'name':[GROUP],'description':['Existing Nextcloud owner binding']}},token=token)
    # A dedicated group is restricted to this immutable subject, independently
    # of future additions to the broader owner policy group.
    api.http('/v1/group/'+GROUP+'/_attr/member',[subject],token=token,method='PUT')
    origin=urllib.parse.urlsplit(callback)
    landing=origin.scheme+'://'+origin.netloc+'/'
    callbacks=[landing+'index.php/apps/user_oidc/code',landing+'apps/user_oidc/code']
    clients=api.http('/v1/oauth2',token=token)
    if not any(c['attrs'].get('name')==[CLIENT] for c in clients):
        api.http('/v1/oauth2/_basic',{'attrs':{'name':[CLIENT],'displayname':['Nextcloud'],
          'oauth2_rs_origin_landing':[landing],
          'oauth2_strict_redirect_uri':['true']}},token=token)
    api.http('/v1/oauth2/'+CLIENT+'/_attr/oauth2_rs_origin',callbacks,token=token)
    api.http('/v1/oauth2/'+CLIENT+'/_attr/oauth2_strict_redirect_uri',['true'],token=token)
    api.http('/v1/oauth2/'+CLIENT+'/_scopemap/'+GROUP,['openid','profile','email'],token=token)
    api.http('/v1/oauth2/'+CLIENT+'/_claimmap/nextcloud_uid/'+GROUP,[uid],token=token)
    api.http('/v1/oauth2/'+CLIENT+'/_claimmap/nextcloud_uid','ssv',token=token)
    checked=api.http('/v1/oauth2/'+CLIENT,token=token)['attrs']
    if sorted(checked.get('oauth2_rs_origin',[]))!=sorted(callbacks) or checked.get('oauth2_strict_redirect_uri')!=['true'] or checked.get('oauth2_allow_insecure_client_disable_pkce',['false'])!=['false']:
        raise RuntimeError('Native client policy mismatch')
    secret=api.http('/v1/oauth2/'+CLIENT+'/_basic_secret',token=token)
    if not isinstance(secret,str) or len(secret)<20:raise RuntimeError('Missing client secret')
    return {'ownerSubject':subject,'nextcloudUid':uid,'clientSecret':secret}
