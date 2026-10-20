# Recruteurs : répondre, retrouver, préparer un appel

Un message de recruteur est toujours une règle d'arrêt : tu ne réponds jamais à sa
place. Tu identifies, tu prépares, l'utilisateur envoie et parle lui-même.

## 1. Identifier : « c'est qui X ? »

L'appel ou le mail vient souvent d'un intermédiaire (ESN, cabinet, plateforme
freelance) dont l'utilisateur n'a pas retenu le nom.

```bash
JS=~/.claude/skills/jobsearch/scripts
python3 $JS/recap.py --find "X"     # nom d'entreprise, de cabinet, de client, de contact, ou numéro
```

- Cherche aussi par numéro de téléphone (avec et sans espaces, avec `+33`) et par
  domaine de l'adresse e-mail.
- Plusieurs résultats : liste-les avec date d'envoi, poste et canal, et demande lequel.
- Aucun résultat : dis-le clairement. Ce n'est peut-être pas une candidature envoyée
  (chasse directe, CVthèque, profil LinkedIn). Ne rattache pas le contact à une fiche
  au hasard.
- Une fois identifié : ajoute le contact dans `contacts` (nom, rôle, téléphone, e-mail)
  et une ligne dans `suivi` de la fiche (`~/Documents/jobsearch/candidatures/<dossier>.json`),
  puis `python3 $JS/recap.py --check`. Format : `jobsearch/references/recap.md`.

## 2. Répondre à un mail ou un message

Tu rédiges un **brouillon** que l'utilisateur relit et envoie lui-même, depuis sa
messagerie. Tu ne cliques pas sur Envoyer, même si la plateforme `email` est en `auto` :
le mandat couvre les candidatures, pas la conversation avec un recruteur.

Règles du brouillon :

- **Court** : 3 à 6 lignes. Répondre à ce qui est demandé, rien de plus.
- **Poli et sobre** : formule d'appel et de fin simples. Pas d'enthousiasme surjoué,
  pas de remerciements en cascade.
- **Le style de l'utilisateur, pas celui du recruteur.** Ne reprends ni ses tournures,
  ni son registre, ni ses emojis, ni sa mise en forme. Si l'utilisateur a déjà écrit des
  mails dans la conversation ou dans le dossier, aligne-toi sur eux. Sinon : phrases
  courtes, vouvoiement, ton neutre. Applique les règles anti-IA du skill cv (ni tiret
  cadratin, ni point-virgule, pas de formules creuses).
- **Pas de redite** : ne répète pas le téléphone ou l'e-mail s'ils sont dans le CV ou
  la signature déjà envoyés. Donne-les seulement si le recruteur les demande.
- **Créneaux** : propose des créneaux seulement si l'utilisateur te les a donnés. Sinon
  écris `[créneaux à compléter]` et signale-le.
- **Prétentions, disponibilité, statut** : reprends exactement ce qui a été répondu dans
  le formulaire (`reponses_formulaire` de la fiche) et le profil. Si le recruteur demande
  autre chose (salaire actuel, autre client, autre contrat), ne tranche pas : pose la
  question à l'utilisateur.
- **Zéro invention** : aucun fait absent du CV master, du profil ou de la lettre envoyée.
- Signature : `lettres.signature` du profil.
- Pièce jointe demandée : indique le chemin du PDF déjà envoyé, ne régénère pas un CV
  différent sans le dire.

Montre le brouillon dans le chat, avec en dessous ce que tu as supposé et ce qu'il doit
vérifier. Ajoute l'échange dans `suivi`.

## 3. Préparer un appel ou un entretien

Produis une fiche courte, lisible en deux minutes, dans le chat ou dans
`~/Documents/jobsearch/candidatures/<dossier>-appel.md` s'il la veut sous la main.

1. **Qui appelle et pour quoi** : intermédiaire, client final, autres noms de
   l'entreprise, poste, contrat, lieu, rythme, date d'envoi et canal. Source : la fiche
   récap (`recap.py --find`) et jobs.db.
2. **La fiche de poste complète** : relis l'annonce entière (`jobs.py show <uid>` ou
   `~/Documents/jobsearch/offres/…md`). Si elle a disparu, dis-le et travaille avec
   la copie locale.
3. **L'entreprise** : recherche web sur l'entreprise et le client final (activité, taille,
   produits, actualité récente, stack si publiée). **Chaque information avec sa source
   (lien).** Rien de non sourcé, pas de chiffre approximatif présenté comme sûr.
4. **Ce qu'il a dit** : le bloc `fiche.ce_que_jai_dit` et `reponses_formulaire`. C'est ce
   qu'il devra assumer. Relis la lettre réellement envoyée.
5. **Points faibles, honnêtement** : les écarts entre l'annonce et le CV master
   (`mots-cles.md` du dossier), chacun avec une réponse vraie (« Ta réponse : … »).
   Une compétence `a_la_competence: non` du profil se dit telle quelle, avec ce qui s'en
   rapproche réellement dans son parcours.
6. **Prétentions** : la réponse déjà donnée, le minimum du profil, et la marge éventuelle.
   Rappelle de ne pas descendre sous le minimum pendant l'appel sans y avoir réfléchi.
7. **Questions à poser** : 3 à 5 questions qui montrent qu'il a lu l'annonce (équipe,
   projet, client final, rythme, process de recrutement, prochaine étape).
8. **Questions probables** avec une réponse courte à la première personne, reprises de
   `fiche.questions_probables` et complétées si besoin.

Après l'appel, quand il le raconte : ligne dans `suivi`, contact dans `contacts`, statut
`jobs.py status <uid> entretien` ou `refuse` selon le cas.
