
# 📊 S&P 500 Swing Scanner avec Polygon.io & Streamlit

Ce projet est une application Streamlit qui scanne les actions du S&P 500 pour détecter des signaux d'achat à l'aide d'indicateurs techniques :

- **UT Bot simplifié**
- **MACD (5,13,4)**
- **Stochastique (8,5,3)**
- **ADX (14)**
- **OBV avec moyenne mobile**

Les données sont récupérées via l'API de [Polygon.io](https://polygon.io/) sur une période d'un an, en bougies journalières (daily).

## 🚀 Fonctionnalités

- Scan asynchrone de tous les titres du S&P 500
- Affichage des tickers avec signaux d'achat
- Téléchargement des résultats au format CSV
- Interface simple et interactive avec Streamlit

## 🛠️ Installation

1. Clonez le dépôt :
```bash
git clone https://github.com/ton-utilisateur/ton-repo.git
cd ton-repo
```

2. Installez les dépendances :
```bash
pip install -r requirements.txt
```

3. Lancez l'application :
```bash
streamlit run streamlit_polygon_sp500.py
```

## 🔑 Configuration

Le script utilise une clé API Polygon.io intégrée. Pour des raisons de sécurité, il est recommandé de :

- créer un fichier `.env` et d'y mettre votre clé :
  ```
  POLYGON_API_KEY=your_api_key_here
  ```
- puis de modifier le script pour lire cette clé depuis l’environnement :
  ```python
  import os
  API_KEY = os.getenv("POLYGON_API_KEY")
  ```

## 📎 Fichiers inclus

- `streamlit_polygon_sp500.py` : l'application Streamlit
- `requirements.txt` : les dépendances Python
- `README.md` : ce fichier

## 📈 Exemples futurs à intégrer

- Visualisation des signaux sur des graphiques
- Options de filtrage (prix, volume, secteur)
- Intégration à Discord ou par email

## 📄 Licence

Projet libre pour usage personnel et éducatif. Redistribution commerciale des données de Polygon.io non autorisée.

---
*Créé par [VotreNom]* – avec ❤️ pour les swing traders 📈
