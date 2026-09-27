# Guide complet : compte secondaire et installation de Deepal Alternative

Guide pas à pas pour connecter votre voiture Changan/Deepal à Home Assistant avec l'intégration
**Deepal Alternative**. Il couvre tout le processus : de la création du compte secondaire dans
l'application My Changan à l'installation de l'intégration avec HACS et sa configuration.

## Sommaire

1. [Pourquoi utiliser un compte secondaire](#pourquoi-utiliser-un-compte-secondaire)
2. [Conditions préalables](#conditions-préalables)
3. [Partie 1 : compte secondaire dans My Changan](#partie-1--compte-secondaire-dans-my-changan)
4. [Partie 2 : installation de l'intégration](#partie-2--installation-de-lintégration)
5. [Remarques et dépannage](#remarques-et-dépannage)

## Pourquoi utiliser un compte secondaire

L'intégration se connecte à la plateforme officielle My Changan. Un même compte ne peut pas
maintenir deux sessions actives en même temps : si Home Assistant se connecte avec votre compte
principal, l'application mobile peut être déconnectée, et si vous vous reconnectez à l'application,
la session de Home Assistant est invalidée.

La solution recommandée est de créer un **compte secondaire**, de partager la voiture depuis le
compte principal et d'utiliser uniquement le compte secondaire dans Home Assistant. Votre compte
principal continue ainsi de fonctionner normalement sur le téléphone.

## Conditions préalables

- Un véhicule Deepal compatible (S05, S07) lié à un compte My Changan.
- Un accès à l'application **My Changan** avec le compte principal.
- Une adresse e-mail ou un numéro de téléphone différent pour le compte secondaire.
- Home Assistant 2026.3.0 ou version ultérieure.
- [HACS](https://hacs.xyz/docs/use/download/download/) installé. Si vous ne l'avez pas encore, suivez
  les instructions d'installation officielles sur <https://hacs.xyz/docs/use/download/download/>.

## Partie 1 : compte secondaire dans My Changan

### 1. Créer le compte secondaire

1. Ouvrez l'application **My Changan** et créez un nouveau compte avec une adresse e-mail ou un
   numéro de téléphone différent de celui de votre compte principal.
2. Notez les identifiants (e-mail/téléphone et code d'accès) : ce sont ceux que vous utiliserez dans
   Home Assistant.

### 2. Partager le véhicule depuis le compte principal

1. Déconnectez-vous du compte secondaire et connectez-vous à l'application avec le **compte
   principal**.
2. Appuyez sur le bouton **partager** de l'écran principal.
3. Invitez le compte secondaire que vous venez de créer, en indiquant une période de validité
   permanente.

### 3. Accepter l'accès et créer le mot de passe de contrôle

1. Déconnectez-vous du **compte principal** dans l'application et connectez-vous avec le **compte
   secondaire**.
2. Acceptez l'accès à la voiture partagée.
3. Allez dans le **centre personnel** (profil) et appuyez sur **Mon véhicule**.
4. Sélectionnez la voiture partagée.
5. Appuyez sur **Mot de passe de contrôle du véhicule** et créez un mot de passe (code PIN).
   Notez-le : c'est le code PIN que Home Assistant demandera pour les commandes des portes, des
   vitres et du coffre.

> Si vous ne trouvez pas cette option dans votre version de l'application, essayez de baisser les
> vitres depuis l'application : elle vous demandera de créer le code PIN de contrôle. Créez-le et
> vérifiez que la commande fonctionne.

### 4. Revenir au compte principal

1. Déconnectez-vous du compte secondaire et reconnectez-vous avec le **compte principal** sur le
   téléphone.
2. Le compte principal reste propriétaire du véhicule ; le secondaire n'est utilisé que dans Home
   Assistant.

## Partie 2 : installation de l'intégration

### 5. Installer HACS (si vous ne l'avez pas encore)

HACS est le gestionnaire d'intégrations personnalisées de Home Assistant. Si vous ne l'avez pas
encore installé, suivez le guide officiel : <https://hacs.xyz/docs/use/download/download/>. Une fois
installé, l'onglet **HACS** apparaît dans la barre latérale de Home Assistant.

### 6. Ajouter le dépôt à HACS

1. Dans Home Assistant, ouvrez l'onglet **HACS**.
2. Ouvrez le menu à trois points (⋮) en haut à droite et choisissez **Dépôts personnalisés**.
3. Collez l'URL du dépôt :
   `https://github.com/Sunek0/ha-deepal-alternative`
4. Dans **Catégorie**, sélectionnez **Intégration** et appuyez sur **Ajouter**.

### 7. Installer Deepal Alternative et redémarrer

1. Dans HACS, recherchez **Deepal Alternative** (vous pouvez utiliser la recherche de l'onglet ou la
   catégorie **Intégrations**).
2. Ouvrez la fiche et appuyez sur **Télécharger**.
3. **Redémarrez Home Assistant** pour charger la nouvelle intégration.

### 8. Ajouter l'intégration

1. Allez dans **Paramètres → Appareils et services**.
2. Appuyez sur **Ajouter une intégration** et recherchez **Deepal Alternative**.
3. Dans **Plateforme**, choisissez **International (Europe)** (l'option SDA (China) est réservée aux
   comptes de Chine continentale avec un access token).
4. Dans **Méthode de connexion**, choisissez comment votre compte secondaire se connecte :
   - **Email code** : un code de vérification est envoyé à l'adresse e-mail.
   - **Phone/SMS code** : un code de vérification est envoyé par SMS au mobile.
5. Remplissez les champs du formulaire :
   - **Pays de vente** : le pays enregistré dans votre compte My Changan (par exemple, l'Espagne).
   - **E-mail** ou **Numéro de mobile** (sans indicatif) du compte **secondaire**.
6. Attendez le code de vérification (e-mail ou SMS) et saisissez-le dans **Code de vérification**.
7. L'intégration valide le compte et crée un appareil par véhicule. Terminé.

### 9. Enregistrer le code PIN de contrôle à distance

Cette étape n'est **nécessaire que** pour utiliser les commandes signées (verrouillage des portes,
vitres et coffre) et pour que Home Assistant crée leurs entités :

1. Allez dans **Paramètres → Appareils et services → Deepal Alternative**.
2. Appuyez sur **Configurer**.
3. Dans **Code PIN de contrôle à distance**, saisissez le mot de passe que vous avez créé à l'étape
   3 avec le compte secondaire.
4. Enregistrez. Les entités des portes, des vitres et du coffre apparaissent sur l'appareil de la
   voiture.

### 10. Vérifier que cela fonctionne

- Ouvrez la page de l'appareil du véhicule : vous devriez voir les capteurs de batterie,
  d'autonomie, de charge et les autres données de télémétrie.
- Testez une commande sûre (par exemple, allumer les feux ou la climatisation) et confirmez que la
  voiture répond.
- Les commandes qui dépendent du code PIN (portes, vitres, coffre) sont signées avec le code PIN
  créé avec le compte secondaire ; si elles échouent, revérifiez l'étape 9.

## Remarques et dépannage

- **Je ne peux rien contrôler** : vérifiez d'abord si l'application officielle peut le faire avec le
  même compte. La voiture refuse parfois les commandes à distance tant qu'elle n'a pas roulé
  quelques minutes.
- **« Remote control PIN is not set » alors que j'ai déjà enregistré le code PIN** : le code PIN n'a
  pas été créé avec le compte utilisé par Home Assistant. Connectez-vous à l'application avec le
  compte secondaire, créez le code PIN (étape 3) et enregistrez-le à nouveau dans les options de
  l'intégration.
- **Home Assistant demande de se reconnecter** : la session a été invalidée depuis l'application ou
  un autre appareil. Reconnectez-vous ; avec le compte secondaire, c'est beaucoup plus rare.
- **Les valeurs semblent obsolètes** : la voiture ne rapporte la télémétrie que lorsqu'elle est
  éveillée ; l'intégration affiche la dernière lecture connue jusqu'à ce qu'elle rapporte à nouveau.
- **Avertissement** : projet non officiel, sans lien avec Changan Automobile. Les commandes à
  distance agissent sur la voiture réelle : assurez-vous que c'est sans danger avant d'utiliser les
  serrures, les vitres, le coffre, la climatisation, les feux ou le klaxon.
