import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate('firebase-credentials.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Sample Spanish episodes
spanish_episodes = [
    {
        "id": "spanish_1_1",
        "title": "Greetings and Family",
        "vocabulary": ["hola", "adiós", "familia", "mamá", "papá"],
        "story_context": "Meeting a Spanish family in their home",
        "difficulty": "beginner",
        "estimated_duration": 300,
        "learning_objectives": ["Basic greetings", "Family members"]
    },
    {
        "id": "spanish_1_2",
        "title": "Farm Animals",
        "vocabulary": ["gato", "perro", "vaca", "caballo", "cerdo"],
        "story_context": "Adventure on a Spanish farm with friendly animals",
        "difficulty": "beginner",
        "estimated_duration": 400,
        "learning_objectives": ["Animal names", "Animal sounds"]
    },
    {
        "id": "spanish_1_3",
        "title": "Colors and Shapes",
        "vocabulary": ["rojo", "azul", "verde", "círculo", "cuadrado"],
        "story_context": "Painting a colorful mural in a Spanish art class",
        "difficulty": "beginner",
        "estimated_duration": 350,
        "learning_objectives": ["Basic colors", "Simple shapes"]
    }
]

# Upload episodes
for episode in spanish_episodes:
    doc_id = episode.pop('id')
    db.collection('episodes').document(doc_id).set(episode)
    print(f"Created episode: {doc_id}")

print("Firebase content setup complete!")