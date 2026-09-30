# Rubika Calendar Synchronizer

Ce projet permet de synchroniser un agenda de l'[extranet de rubika](https://extranet.rubika-edu.com/) avec un agenda Google Calendar.

## Setup

### 1. Extranet

Renseigne juste tes identifiants de l'extranet dans un fichier `extranet.json` à la racine de ce projet. Le fichier doit ressembler à ça :

```json
{
    "password": "<VOTRE_MOT_DE_PASSE>",
    "email": "<VOTRE_ADRESSE_MAIL>"
}
```

### 2. Google Calendar

Pour que synchroniser les évènements de l'extranet avec vôtre agenda google, vous devez:

1. **Créer un projet sur Google Cloud**

   - Rends-toi sur la [Google Cloud Console](https://console.cloud.google.com).

   - Connecte-toi avec ton compte Google.

   - Clique sur le sélecteur de projet (en haut à gauche) puis sur `New project` (osef du nom).

2. **Activer l'API Google Calendar**

   - Dans le menu latéral, va dans `API and services > Library`.

   - Recherche `Google Calendar API`.

   - Clique sur la fiche de l'API puis sur `Activer`.

3. **Créer un client et télécharge le certifications**

   - Va dans le `menu latéral > API et services > Écran de consentement OAuth`.

   - Sélectionne `Clients` et clique sur `Create client`.

   - Sélection `Desktop App` (et osef du nom) et cllique sur le bouton `Download JSON`.

   - Renome le fichier que tu vient de télécharger en `credentials.json` et mets le à la racine de ce dossier.

## Usage

Pour éxécuter le code python, vous devez avoir python d'installer sur vôtre machine et écrire dans un terminale ouvert à la racine de ce dossier les commandes suivantes :

```sh
python -m pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

et

```sh
python main.py
```
