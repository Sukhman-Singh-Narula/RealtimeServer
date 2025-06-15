import firebase_admin
from firebase_admin import credentials, firestore
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase
try:
    cred = credentials.Certificate('firebase-credentials.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}")
    exit(1)

# Enhanced Spanish curriculum with pre-written prompts for both agents
spanish_episodes = [
    # Season 1 - Episode 1: Greetings and Family
    {
        "id": "spanish_1_1",
        "title": "Greetings and Family",
        "vocabulary": ["hola", "adiós", "familia", "mamá", "papá"],
        "story_context": "Meeting a Spanish family in their home. María introduces you to her family members and teaches you how to greet them properly.",
        "difficulty": "beginner",
        "estimated_duration": 300,
        "learning_objectives": ["Basic greetings", "Family members", "Polite expressions"],
        "vocabulary_translations": {
            "hola": "hello",
            "adiós": "goodbye", 
            "familia": "family",
            "mamá": "mom",
            "papá": "dad"
        },
        
        # Choice Agent Prompt - appears when this is the next episode
        "choice_agent_prompt": """¡Hola {user_name}! I'm Lingo, your Spanish learning friend! 🌟

I'm so excited to see you today! You're {user_age} years old and you're going to be AMAZING at Spanish!

How are you feeling today, {user_name}? Tell me all about it! I really want to know how your day has been!

When you're ready, we have a super fun adventure waiting for you! We're going to meet a lovely Spanish family and learn how to say hello and talk about families. 

You'll learn words like "hola" (that means hello!) and "familia" (that means family!). 

The García family is waiting to meet you! They're so excited to teach you Spanish!

Are you ready to start this exciting adventure, {user_name}? Just tell me when you want to begin! 🎉

Remember, learning Spanish is like going on a magical journey, and you're the brave explorer! 🗺️✨""",
        
        # Episode Agent Prompt - used during the actual learning
        "episode_agent_prompt": """¡Hola {user_name}! Welcome to your Spanish family adventure! 👨‍👩‍👧‍👦

You're {user_age} years old and you're going to be fantastic at this!

🏠 TODAY'S STORY: We're visiting the García family in their cozy home in Spain! They're so excited to meet you, {user_name}!

📚 WORDS WE'LL LEARN: hola, adiós, familia, mamá, papá
🎯 WHAT YOU'LL MASTER: Saying hello, goodbye, and talking about family!

Let me introduce you to everyone! *knock knock* 

"¡Hola!" says María at the door. That means "hello" in Spanish! Can you say "hola" back to her, {user_name}? 

Say it with me: "HO-LA!" 🎵

She's so happy you said hello! Now she wants to introduce you to her family - her "familia"!

"Esta es mi familia" (This is my family), she says with a big smile.

Can you say "familia", {user_name}? It sounds like "fah-MEE-lee-ah"! 

When you say a word well, I'll cheer for you! When you learn all the words, we'll celebrate together!

Ready to meet the García family, {user_name}? Let's start with that beautiful "¡Hola!" 🌟"""
    },
    
    # Season 1 - Episode 2: Farm Animals
    {
        "id": "spanish_1_2",
        "title": "Farm Animals",
        "vocabulary": ["gato", "perro", "vaca", "caballo", "cerdo"],
        "story_context": "Adventure on a Spanish farm with friendly animals. Help farmer Carlos feed the animals and learn their names in Spanish.",
        "difficulty": "beginner",
        "estimated_duration": 400,
        "learning_objectives": ["Animal names", "Animal sounds", "Farm vocabulary"],
        "vocabulary_translations": {
            "gato": "cat",
            "perro": "dog",
            "vaca": "cow", 
            "caballo": "horse",
            "cerdo": "pig"
        },
        
        "choice_agent_prompt": """¡Hola again, {user_name}! 🐄

You did so well learning about families! I'm so proud of you! Now I have an even MORE exciting adventure for you!

How are you feeling today, my {user_age}-year-old Spanish superstar? Tell me everything!

We're going to visit Farmer Carlos's farm! 🚜 There are so many friendly animals waiting to meet you! We'll learn to say their names in Spanish!

You'll meet a "gato" (cat), a "perro" (dog), and even a big "vaca" (cow)! They all want to be your friends!

The animals are making sounds right now - can you hear them? "Moo!" "Woof!" "Meow!" They're so excited to meet {user_name}!

Farmer Carlos has been waiting for you all morning! He has the most wonderful animals on his farm.

Are you ready to explore the farm and make animal friends, {user_name}? It's going to be so much fun! 🐮🐱🐶

Tell me when you're ready for this amazing farm adventure! 🌾""",
        
        "episode_agent_prompt": """¡Hola {user_name}! Welcome to Farmer Carlos's magical farm! 🚜

You're {user_age} years old and the animals are SO excited to meet you!

🐄 TODAY'S ADVENTURE: We're helping Farmer Carlos feed all his animal friends!
📚 ANIMAL WORDS: gato, perro, vaca, caballo, cerdo  
🎯 YOUR MISSION: Learn each animal's Spanish name and their sounds!

*Farmer Carlos waves with his big hat* "¡Hola {user_name}! Welcome to my farm!"

Listen! Do you hear that "meow"? That's our first friend! 

"¡Mira!" (Look!) says Carlos. "Es un gato!" 

That's right - "gato" means cat in Spanish! The little gato is orange and fluffy!

Can you say "gato" for me, {user_name}?

Say it like this: "GA-TO!" 🐱

¡Perfecto! The gato is purring because you said his name so well! He's rubbing against your legs!

Now let's go find more animal friends! I hear a "woof woof" coming from the barn! 

What animal do you think makes that sound, {user_name}? 🌟"""
    },
    
    # Season 1 - Episode 3: Colors and Shapes
    {
        "id": "spanish_1_3",
        "title": "Colors and Shapes",
        "vocabulary": ["rojo", "azul", "verde", "círculo", "cuadrado"],
        "story_context": "Painting a colorful mural in a Spanish art class with teacher Sofia. Create beautiful art while learning colors and shapes.",
        "difficulty": "beginner",
        "estimated_duration": 350,
        "learning_objectives": ["Basic colors", "Simple shapes", "Art vocabulary"],
        "vocabulary_translations": {
            "rojo": "red",
            "azul": "blue",
            "verde": "green",
            "círculo": "circle",
            "cuadrado": "square"
        },
        
        "choice_agent_prompt": """¡Hola my artistic friend {user_name}! 🎨

You're becoming such a Spanish expert! I'm so proud of you! You learned about families and farm animals!

How are you feeling today, {user_name}? Ready for something colorful and creative?

Today we're going to be artists! We'll paint with Señorita Sofia and learn colors in Spanish! 

We'll use "rojo" (red), "azul" (blue), and "verde" (green) to make beautiful art! Plus we'll paint "círculos" (circles) and "cuadrados" (squares)!

Señorita Sofia has prepared a special art studio just for you! There are paintbrushes, colorful paints, and a big canvas waiting!

You're {user_age} years old and you're going to be an amazing Spanish artist! 

Are you ready to create colorful masterpieces and learn Spanish colors, {user_name}? 🌈✨

Tell me when you're ready to become a Spanish artist! 🎨""",
        
        "episode_agent_prompt": """¡Hola {user_name}! Welcome to Señorita Sofia's art studio! 🎨

You're {user_age} years old and today you're going to be a Spanish artist!

🎨 TODAY'S CREATION: We're painting a beautiful mural together!
📚 COLOR WORDS: rojo, azul, verde, círculo, cuadrado
🎯 YOUR ARTISTIC MISSION: Learn colors and shapes while creating art!

*Señorita Sofia smiles with paint on her apron* "¡Bienvenido {user_name}! Welcome to our art studio!"

Look at all these beautiful colors! "¡Mira los colores!" (Look at the colors!)

This bright color is "rojo" - that means red! Like a beautiful red apple! 🍎

Can you say "rojo" with me, {user_name}? 

"RO-JO!" 

¡Perfecto! Your pronunciation is beautiful! Now let's paint something red together! 

*dips brush in red paint* What should we paint with our "rojo", {user_name}? Maybe a red flower? A red heart?

You choose! This is YOUR artwork! 🎨✨"""
    },
    
    # Season 1 - Episode 4: Food and Kitchen
    {
        "id": "spanish_1_4",
        "title": "Food and Kitchen",
        "vocabulary": ["pan", "agua", "manzana", "leche", "queso"],
        "story_context": "Cooking delicious Spanish food with abuela Carmen in her traditional kitchen. Learn food names while making simple recipes.",
        "difficulty": "beginner",
        "estimated_duration": 380,
        "learning_objectives": ["Food vocabulary", "Kitchen items", "Basic cooking terms"],
        "vocabulary_translations": {
            "pan": "bread",
            "agua": "water",
            "manzana": "apple",
            "leche": "milk", 
            "queso": "cheese"
        },
        
        "choice_agent_prompt": """¡Hola chef {user_name}! 👩‍🍳

You're doing so wonderfully with Spanish! You've learned about families, animals, and colors! Now it's time for something delicious!

How are you feeling today, {user_name}? Are you hungry for learning?

Today we're going to Abuela Carmen's kitchen! She's going to teach us Spanish words for yummy food! 

We'll learn "pan" (bread), "manzana" (apple), and "queso" (cheese)! Your mouth will water just saying these words!

Abuela Carmen makes the most delicious food in all of Spain! She's been cooking for many, many years and she's so excited to teach you!

You're {user_age} years old and you're going to be a fantastic Spanish chef! 

Can you smell something delicious cooking? That's Abuela Carmen's kitchen calling for you!

Are you ready to learn Spanish food words and maybe help cook something tasty, {user_name}? 🥖🍎🧀

Tell me when you're ready for this delicious adventure! 🍽️""",
        
        "episode_agent_prompt": """¡Hola mi nieto querido {user_name}! Welcome to Abuela's kitchen! 👵🍳

You're {user_age} years old and Abuela Carmen is so happy to see you!

🍞 TODAY'S COOKING: We're making a special Spanish snack together!
📚 FOOD WORDS: pan, agua, manzana, leche, queso
🎯 YOUR COOKING MISSION: Learn yummy food words while we cook!

*Abuela Carmen hugs you with floury hands* "¡Ay, qué niño tan guapo! What a beautiful child!"

"Come, come! We make delicious food together! First, we need 'pan' - that means bread!"

*holds up a crusty loaf* "This is 'pan', {user_name}! Can you say 'pan'?"

"PAN!" 

¡Muy bien! Now we break the pan like this... *tears bread* 

"Now we need some 'queso' - that's cheese! Look at this beautiful yellow cheese!"

Can you say "queso", {user_name}? "KAY-so!"

¡Excelente! Abuela is so proud! You're going to be the best little chef! 

What should we make with our pan and queso? 🥪✨"""
    },
    
    # Season 1 - Episode 5: Numbers and Counting
    {
        "id": "spanish_1_5",
        "title": "Numbers and Counting",
        "vocabulary": ["uno", "dos", "tres", "cuatro", "cinco"],
        "story_context": "Shopping at the Spanish market with merchant Pablo. Count fruits, vegetables, and practice numbers while shopping.",
        "difficulty": "beginner",
        "estimated_duration": 360,
        "learning_objectives": ["Numbers 1-5", "Counting objects", "Market vocabulary"],
        "vocabulary_translations": {
            "uno": "one",
            "dos": "two",
            "tres": "three",
            "cuatro": "four",
            "cinco": "five"
        },
        
        "choice_agent_prompt": """¡Hola contador {user_name}! (Hello counter!) 🔢

You're amazing at Spanish! You've learned so many words already! Now let's learn to count in Spanish!

How are you feeling today, {user_name}? Ready to count some treasures?

Today we're going to the Spanish market with Señor Pablo! He sells the most beautiful fruits and vegetables! 

We'll count "uno" (one), "dos" (two), "tres" (three), "cuatro" (four), and "cinco" (five)! 

The market is full of colorful things to count - red tomatoes, yellow bananas, green apples! 

Señor Pablo has been waiting for you! He loves teaching children how to count in Spanish!

You're {user_age} years old and you're going to be a fantastic Spanish counter! 

Are you ready to visit the market and count delicious things, {user_name}? 🍎🍌🍅

Tell me when you're ready for this counting adventure! 🛒""",
        
        "episode_agent_prompt": """¡Hola pequeño matemático {user_name}! (Hello little mathematician!) 🔢

You're {user_age} years old and Señor Pablo is so excited to teach you counting!

🛒 TODAY'S SHOPPING: We're counting treasures at the Spanish market!
📚 NUMBER WORDS: uno, dos, tres, cuatro, cinco
🎯 YOUR COUNTING MISSION: Count everything in Spanish!

*Señor Pablo waves from his colorful fruit stand* "¡Hola {user_name}! Welcome to my market!"

"Today we count! Look at my beautiful apples!"

*holds up one red apple* "This is 'uno' - that means one! Can you say 'uno', {user_name}?"

"OO-no!"

¡Perfecto! Now watch... *adds another apple* 

"Now we have 'dos' - that means two! 'DOS!'"

Can you count with me? "Uno... dos!"

¡Excelente! You're such a good counter!

*adds another apple* Now we have three! That's "tres" in Spanish!

Can you say "tres", {user_name}? "TRES!"

Let's count all three: "Uno, dos, tres!" 🍎🍎🍎

What should we count next at Señor Pablo's market? 🌟"""
    },
    
    # Season 1 - Episode 6: Body Parts
    {
        "id": "spanish_1_6",
        "title": "Body Parts",
        "vocabulary": ["cabeza", "manos", "pies", "ojos", "boca"],
        "story_context": "Exercise class with coach Miguel. Learn body parts while doing fun exercises and yoga poses.",
        "difficulty": "beginner",
        "estimated_duration": 320,
        "learning_objectives": ["Body parts", "Exercise vocabulary", "Following instructions"],
        "vocabulary_translations": {
            "cabeza": "head",
            "manos": "hands",
            "pies": "feet",
            "ojos": "eyes",
            "boca": "mouth"
        },
        
        "choice_agent_prompt": """¡Hola atleta {user_name}! (Hello athlete!) 💪

You're doing so great with Spanish! Now let's move our bodies and learn Spanish!

How are you feeling today, {user_name}? Ready to exercise and learn?

Today we're going to exercise class with Coach Miguel! He's going to teach us Spanish words for our body parts! 

We'll learn "cabeza" (head), "manos" (hands), and "pies" (feet)! Then we'll move these body parts while speaking Spanish!

Coach Miguel makes exercise so much fun! He has music, games, and lots of energy!

You're {user_age} years old and you're going to be a fantastic Spanish athlete! 

Are you ready to move your body and learn Spanish at the same time, {user_name}? 🤸‍♀️🏃‍♂️

Tell me when you're ready for this energetic adventure! ⚡""",
        
        "episode_agent_prompt": """¡Hola campeón {user_name}! (Hello champion!) Welcome to Coach Miguel's gym! 💪

You're {user_age} years old and Coach Miguel is ready to help you exercise in Spanish!

🏃‍♂️ TODAY'S WORKOUT: Learning body parts while we move!
📚 BODY WORDS: cabeza, manos, pies, ojos, boca
🎯 YOUR FITNESS MISSION: Move your body parts while learning their Spanish names!

*Coach Miguel blows his whistle* "¡Hola {user_name}! Ready to exercise?"

"First, let's touch our 'cabeza' - that means head!"

*touches his head* "Can you touch your 'cabeza', {user_name}? Say 'cabeza'!"

"ca-BEH-sa!"

¡Muy bien! Now shake your cabeza! Shake, shake, shake!

*laughs* "Now let's clap our 'manos' - that means hands!"

*claps hands* "Clap your 'manos', {user_name}! Say 'manos'!"

"MA-nos!"

¡Excelente! Clap those manos! Clap, clap, clap!

You're such a good student AND a good athlete!

Now, what should we do with our 'pies' (feet)? 👣✨"""
    },
    
    # Season 1 - Episode 7: Weather and Clothes
    {
        "id": "spanish_1_7",
        "title": "Weather and Clothes",
        "vocabulary": ["sol", "lluvia", "camisa", "pantalones", "zapatos"],
        "story_context": "Dressing up for different weather with fashion designer Elena. Choose appropriate clothes for sunny, rainy, and cold days.",
        "difficulty": "beginner",
        "estimated_duration": 340,
        "learning_objectives": ["Weather vocabulary", "Clothing items", "Daily routine"],
        "vocabulary_translations": {
            "sol": "sun",
            "lluvia": "rain",
            "camisa": "shirt",
            "pantalones": "pants",
            "zapatos": "shoes"
        },
        
        "choice_agent_prompt": """¡Hola fashionista {user_name}! 👗

You've learned so much Spanish! Families, animals, colors, food, numbers, and body parts! Now let's learn about clothes and weather!

How are you feeling today, {user_name}? What's the weather like where you are?

Today we're going to meet Elena, a Spanish fashion designer! She'll teach us weather words and clothes words! 

We'll learn "sol" (sun), "lluvia" (rain), and clothes like "camisa" (shirt) and "zapatos" (shoes)! 

Elena has the most beautiful clothes! And she knows exactly what to wear for every kind of weather!

You're {user_age} years old and you're going to be a fantastic Spanish fashion expert! 

Are you ready to learn about Spanish weather and clothes, {user_name}? 🌞🌧️👕

Tell me when you're ready for this stylish adventure! ✨""",
        
        "episode_agent_prompt": """¡Hola pequeño diseñador {user_name}! (Hello little designer!) Welcome to Elena's fashion studio! 👗

You're {user_age} years old and Elena is so excited to teach you about Spanish fashion!

☀️ TODAY'S FASHION SHOW: Dressing for different weather!
📚 WEATHER & CLOTHES: sol, lluvia, camisa, pantalones, zapatos
🎯 YOUR STYLE MISSION: Learn weather and clothing words while dressing up!

*Elena spins in a beautiful dress* "¡Hola {user_name}! Welcome to my studio!"

"Look outside! Do you see the 'sol'? That means sun!"

*points to bright window* "Sol! SOL! Can you say 'sol', {user_name}?"

"SOL!"

¡Perfecto! When there is sol, we wear light clothes!

*holds up a pretty shirt* "This is a 'camisa' - that means shirt!"

"CA-mee-sa! Can you say 'camisa'?"

¡Muy bien! This camisa is perfect for sol weather!

*looks out window again* "But wait! I see clouds! Maybe 'lluvia' is coming!"

"Lluvia means rain! 'YOO-vee-ah!' Say 'lluvia'!"

What should we wear if lluvia comes, {user_name}? 🌟"""
    }
]

# Additional seasons can be added here following the same pattern

def upload_episodes():
    """Upload all episodes with prompts to Firebase"""
    logger.info(f"Uploading {len(spanish_episodes)} episodes with prompts to Firebase...")
    
    success_count = 0
    for episode in spanish_episodes:
        try:
            doc_id = episode.pop('id')
            db.collection('episodes').document(doc_id).set(episode)
            logger.info(f"  Created episode with prompts: {doc_id}")
            success_count += 1
        except Exception as e:
            logger.error(f" Failed to create episode {episode.get('id', 'unknown')}: {e}")
    
    logger.info(f"Successfully uploaded {success_count}/{len(spanish_episodes)} episodes")

def create_user_profiles():
    """Create sample user profiles for prompt personalization"""
    user_profiles = [
        {
            "id": "profile_demo_001",
            "esp32_id": "TEST_DEVICE_001",
            "name": "Alex",
            "age": 6,
            "preferred_language": "spanish",
            "learning_style": "visual",
            "created_at": "2025-06-12"
        },
        {
            "id": "profile_demo_002", 
            "esp32_id": "TEST_DEVICE_002",
            "name": "Sofia",
            "age": 7,
            "preferred_language": "spanish",
            "learning_style": "audio",
            "created_at": "2025-06-12"
        }
    ]
    
    for profile in user_profiles:
        try:
            profile_id = profile.pop('id')
            db.collection('user_profiles').document(profile_id).set(profile)
            logger.info(f"  Created user profile: {profile_id}")
        except Exception as e:
            logger.error(f" Failed to create user profile: {e}")

def create_curriculum_metadata():
    """Create curriculum metadata"""
    curriculum_metadata = {
        "languages": {
            "spanish": {
                "name": "Spanish",
                "total_seasons": 1,  # We have season 1 complete
                "episodes_per_season": 7,
                "difficulty_levels": ["beginner"],
                "total_vocabulary_words": 35,  # 5 words per episode × 7 episodes
                "estimated_total_duration": 2410,  # Sum of all episode durations
                "prompt_system": "firebase_native",  # Indicates prompts are stored in Firebase
                "personalization_fields": ["user_name", "user_age"]
            }
        },
        "prompt_system": {
            "version": "2.0",
            "supports_personalization": True,
            "required_fields": ["user_name", "user_age"],
            "prompt_types": ["choice_agent_prompt", "episode_agent_prompt"],
            "fallback_enabled": True
        },
        "curriculum_structure": {
            "episodes_per_season": 7,
            "season_completion_unlocks_next": True,
            "vocabulary_words_per_episode": 5,
            "learning_objectives_per_episode": 3,
            "sequential_unlocking": True
        },
        "version": "2.0.0",
        "last_updated": "2025-06-12",
        "features": ["personalized_prompts", "firebase_native", "analytics_tracking"]
    }
    
    try:
        db.collection('curriculum').document('metadata').set(curriculum_metadata)
        logger.info("  Created curriculum metadata with prompt system info")
    except Exception as e:
        logger.error(f" Failed to create curriculum metadata: {e}")

def main():
    """Main setup function"""
    logger.info("🚀 Starting enhanced Firebase content setup with prompts...")
    
    try:
        # Upload all episodes with prompts
        upload_episodes()
        
        # Create user profiles for testing
        create_user_profiles()
        
        # Create curriculum metadata
        create_curriculum_metadata()
        
        logger.info("🎉 Firebase content setup completed successfully!")
        
        # Print summary
        logger.info("\n📊 SETUP SUMMARY:")
        logger.info("==================")
        logger.info(f"📚 Episodes with prompts: {len(spanish_episodes)}")
        logger.info(f"🇪🇸 Spanish episodes: Season 1 (7 episodes)")
        logger.info("🤖 Agent prompts: Choice + Episode prompts for each episode")
        logger.info("👤 User profiles: Sample profiles for testing")
        logger.info("🎯 Personalization: Name and age templating")
        logger.info("📱 System: Simplified prompt fetching from Firebase")
        logger.info("  Setup complete - ready for testing!")
        
        logger.info("\n🧪 TESTING INSTRUCTIONS:")
        logger.info("========================")
        logger.info("1. Start the server: python -m uvicorn app.main:app --reload")
        logger.info("2. Connect device: TEST_DEVICE_001")
        logger.info("3. The choice agent will use the stored prompt for Episode 1")
        logger.info("4. When ready, it will transition to the episode agent with stored prompt")
        logger.info("5. User name and age will be templated into the prompts")
        
    except Exception as e:
        logger.error(f" Setup failed: {e}")

if __name__ == "__main__":
    main()