"""
Seed data for SwipeNight — works fully offline (no external API keys needed).

50 movies + 30 series + 30 anime, plus fake users, ratings, reviews and a demo
room. Poster/backdrop images use a deterministic public image CDN so the UI is
always populated. When TMDB / AniList / Trakt keys are added later, the same
content documents are upserted by the external service layer (see services/).
"""
import random
import uuid
from datetime import datetime, timedelta, timezone

PROVIDERS = ["Netflix", "Disney+", "Prime Video", "Apple TV+", "Max", "Crunchyroll"]


def _slug(t):
    return "".join(c for c in t.lower() if c.isalnum() or c == " ").replace(" ", "-")


def _poster(t):
    return f"https://picsum.photos/seed/{_slug(t)}-p/400/600"


def _backdrop(t):
    return f"https://picsum.photos/seed/{_slug(t)}-b/900/506"


# (title, year, genres, runtime, popularity, rating, votes, providers, cast, crew, studio, keywords, overview)
MOVIES = [
    ("Dune: Part Two", 2024, ["Sci-Fi", "Adventure", "Drama"], 166, 95, 8.4, 6200, ["Max", "Netflix"], ["Timothée Chalamet", "Zendaya"], "Denis Villeneuve", "Legendary", ["desert", "dystopia", "war", "prophecy"], "Paul Atreides unites with the Fremen to wage war against House Harkonnen."),
    ("Oppenheimer", 2023, ["Drama", "Thriller", "Crime"], 180, 92, 8.3, 7800, ["Prime Video"], ["Cillian Murphy", "Robert Downey Jr."], "Christopher Nolan", "Universal", ["history", "war", "science", "biography"], "The story of J. Robert Oppenheimer and the creation of the atomic bomb."),
    ("Interstellar", 2014, ["Sci-Fi", "Drama", "Adventure"], 169, 90, 8.6, 18000, ["Prime Video", "Max"], ["Matthew McConaughey", "Anne Hathaway"], "Christopher Nolan", "Paramount", ["space", "time", "wormhole", "family"], "Explorers travel through a wormhole in space to ensure humanity's survival."),
    ("Inception", 2010, ["Sci-Fi", "Action", "Thriller"], 148, 88, 8.8, 24000, ["Netflix", "Max"], ["Leonardo DiCaprio", "Joseph Gordon-Levitt"], "Christopher Nolan", "Warner Bros", ["dreams", "heist", "mind", "reality"], "A thief who steals corporate secrets through dream-sharing technology."),
    ("The Dark Knight", 2008, ["Action", "Crime", "Drama"], 152, 89, 9.0, 27000, ["Max"], ["Christian Bale", "Heath Ledger"], "Christopher Nolan", "Warner Bros", ["batman", "joker", "vigilante", "gotham"], "Batman faces the Joker, a criminal mastermind who plunges Gotham into chaos."),
    ("Parasite", 2019, ["Thriller", "Drama", "Comedy"], 132, 87, 8.5, 16000, ["Max", "Prime Video"], ["Song Kang-ho", "Choi Woo-shik"], "Bong Joon-ho", "CJ Entertainment", ["class", "family", "satire", "korean"], "A poor family schemes to become employed by a wealthy household."),
    ("Whiplash", 2014, ["Drama", "Thriller"], 106, 80, 8.5, 9000, ["Netflix"], ["Miles Teller", "J.K. Simmons"], "Damien Chazelle", "Sony", ["music", "ambition", "jazz", "mentor"], "A young drummer is pushed to his limits by a ruthless instructor."),
    ("Blade Runner 2049", 2017, ["Sci-Fi", "Drama", "Thriller"], 164, 82, 8.0, 12000, ["Netflix"], ["Ryan Gosling", "Harrison Ford"], "Denis Villeneuve", "Warner Bros", ["replicant", "future", "noir", "identity"], "A young blade runner uncovers a secret that could plunge society into chaos."),
    ("Mad Max: Fury Road", 2015, ["Action", "Adventure", "Sci-Fi"], 120, 84, 8.1, 14000, ["Max"], ["Tom Hardy", "Charlize Theron"], "George Miller", "Warner Bros", ["apocalypse", "chase", "desert", "survival"], "In a post-apocalyptic wasteland, a woman rebels against a tyrant."),
    ("The Matrix", 1999, ["Sci-Fi", "Action"], 136, 83, 8.7, 20000, ["Max"], ["Keanu Reeves", "Laurence Fishburne"], "The Wachowskis", "Warner Bros", ["simulation", "rebellion", "hacker", "reality"], "A hacker discovers reality is a simulation and joins a rebellion."),
    ("Pulp Fiction", 1994, ["Crime", "Drama", "Thriller"], 154, 81, 8.9, 21000, ["Netflix"], ["John Travolta", "Samuel L. Jackson"], "Quentin Tarantino", "Miramax", ["nonlinear", "crime", "dialogue", "gangster"], "The lives of two mob hitmen, a boxer and others intertwine."),
    ("Fight Club", 1999, ["Drama", "Thriller"], 139, 80, 8.8, 22000, ["Prime Video"], ["Brad Pitt", "Edward Norton"], "David Fincher", "Fox", ["identity", "anarchy", "consumerism", "twist"], "An insomniac and a soap maker form an underground fight club."),
    ("Get Out", 2017, ["Horror", "Thriller"], 104, 79, 7.7, 11000, ["Netflix", "Max"], ["Daniel Kaluuya", "Allison Williams"], "Jordan Peele", "Blumhouse", ["race", "twist", "suspense", "social"], "A young man uncovers disturbing secrets at his girlfriend's family estate."),
    ("La La Land", 2016, ["Romance", "Drama", "Comedy"], 128, 78, 8.0, 13000, ["Prime Video"], ["Ryan Gosling", "Emma Stone"], "Damien Chazelle", "Lionsgate", ["music", "love", "dreams", "jazz"], "A jazz musician and an actress fall in love while pursuing their dreams."),
    ("Joker", 2019, ["Crime", "Drama", "Thriller"], 122, 85, 8.2, 17000, ["Max"], ["Joaquin Phoenix"], "Todd Phillips", "Warner Bros", ["mental", "gotham", "origin", "society"], "A failed comedian descends into madness and becomes a criminal mastermind."),
    ("Everything Everywhere All at Once", 2022, ["Sci-Fi", "Comedy", "Adventure"], 139, 86, 8.0, 12000, ["Prime Video"], ["Michelle Yeoh", "Ke Huy Quan"], "Daniels", "A24", ["multiverse", "family", "absurd", "identity"], "A laundromat owner must connect with parallel-universe versions of herself."),
    ("The Social Network", 2010, ["Drama", "Crime"], 120, 74, 7.8, 10000, ["Netflix"], ["Jesse Eisenberg", "Andrew Garfield"], "David Fincher", "Sony", ["startup", "betrayal", "tech", "ambition"], "The founding of Facebook and the lawsuits that followed."),
    ("Gone Girl", 2014, ["Thriller", "Drama", "Crime"], 149, 80, 8.1, 11000, ["Prime Video"], ["Ben Affleck", "Rosamund Pike"], "David Fincher", "Fox", ["marriage", "twist", "missing", "media"], "A man becomes the prime suspect in his wife's disappearance."),
    ("Arrival", 2016, ["Sci-Fi", "Drama"], 116, 79, 7.9, 10000, ["Max"], ["Amy Adams", "Jeremy Renner"], "Denis Villeneuve", "Paramount", ["aliens", "language", "time", "first-contact"], "A linguist works to communicate with alien visitors."),
    ("Ex Machina", 2014, ["Sci-Fi", "Drama", "Thriller"], 108, 75, 7.7, 9000, ["Netflix"], ["Alicia Vikander", "Oscar Isaac"], "Alex Garland", "A24", ["ai", "robot", "isolation", "consciousness"], "A programmer evaluates the human qualities of an advanced humanoid AI."),
    ("Prisoners", 2013, ["Thriller", "Crime", "Drama"], 153, 76, 8.2, 9500, ["Prime Video"], ["Hugh Jackman", "Jake Gyllenhaal"], "Denis Villeneuve", "Warner Bros", ["kidnapping", "morality", "detective", "mystery"], "A father takes matters into his own hands when his daughter goes missing."),
    ("Sicario", 2015, ["Action", "Crime", "Thriller"], 121, 74, 7.6, 8000, ["Netflix"], ["Emily Blunt", "Benicio del Toro"], "Denis Villeneuve", "Lionsgate", ["cartel", "border", "fbi", "moral"], "An FBI agent is enlisted to bring down a drug cartel."),
    ("No Country for Old Men", 2007, ["Crime", "Thriller", "Drama"], 122, 73, 8.2, 9800, ["Max"], ["Javier Bardem", "Josh Brolin"], "Coen Brothers", "Paramount", ["chase", "money", "fate", "violence"], "A hunter stumbles upon drug money and is pursued by a killer."),
    ("The Grand Budapest Hotel", 2014, ["Comedy", "Adventure", "Drama"], 99, 72, 8.1, 8500, ["Disney+"], ["Ralph Fiennes", "Tony Revolori"], "Wes Anderson", "Fox Searchlight", ["whimsical", "heist", "europe", "quirky"], "A concierge and a lobby boy become embroiled in a theft."),
    ("John Wick", 2014, ["Action", "Thriller", "Crime"], 101, 83, 7.4, 13000, ["Prime Video"], ["Keanu Reeves"], "Chad Stahelski", "Lionsgate", ["assassin", "revenge", "gun-fu", "underworld"], "A retired hitman seeks vengeance for the killing of his dog."),
    ("Gladiator", 2000, ["Action", "Adventure", "Drama"], 155, 78, 8.5, 15000, ["Prime Video"], ["Russell Crowe", "Joaquin Phoenix"], "Ridley Scott", "DreamWorks", ["rome", "revenge", "arena", "empire"], "A betrayed Roman general seeks revenge as a gladiator."),
    ("The Prestige", 2006, ["Drama", "Thriller", "Sci-Fi"], 130, 76, 8.5, 13000, ["Max"], ["Hugh Jackman", "Christian Bale"], "Christopher Nolan", "Warner Bros", ["magic", "rivalry", "obsession", "twist"], "Two rival magicians engage in a deadly competition."),
    ("Memento", 2000, ["Thriller", "Crime", "Drama"], 113, 72, 8.4, 12000, ["Netflix"], ["Guy Pearce"], "Christopher Nolan", "Newmarket", ["memory", "revenge", "nonlinear", "mystery"], "A man with short-term memory loss hunts his wife's killer."),
    ("Shutter Island", 2010, ["Thriller", "Drama", "Crime"], 138, 79, 8.2, 13000, ["Netflix"], ["Leonardo DiCaprio"], "Martin Scorsese", "Paramount", ["asylum", "twist", "investigation", "mind"], "A marshal investigates a disappearance at a remote psychiatric facility."),
    ("Knives Out", 2019, ["Crime", "Comedy", "Drama"], 130, 80, 7.9, 11000, ["Prime Video"], ["Daniel Craig", "Ana de Armas"], "Rian Johnson", "Lionsgate", ["whodunit", "family", "detective", "mystery"], "A detective investigates the death of a wealthy crime novelist."),
    ("Drive", 2011, ["Crime", "Drama", "Thriller"], 100, 71, 7.8, 9000, ["Prime Video"], ["Ryan Gosling"], "Nicolas Winding Refn", "FilmDistrict", ["getaway", "neon", "stoic", "violence"], "A stunt driver moonlights as a getaway driver and gets in over his head."),
    ("Nightcrawler", 2014, ["Crime", "Drama", "Thriller"], 117, 70, 7.8, 8000, ["Netflix"], ["Jake Gyllenhaal"], "Dan Gilroy", "Open Road", ["media", "crime", "obsession", "ambition"], "A driven man enters the world of crime journalism in LA."),
    ("The Wolf of Wall Street", 2013, ["Crime", "Comedy", "Drama"], 180, 79, 8.2, 14000, ["Prime Video"], ["Leonardo DiCaprio", "Jonah Hill"], "Martin Scorsese", "Paramount", ["greed", "wall-street", "excess", "fraud"], "The rise and fall of a corrupt stockbroker."),
    ("Django Unchained", 2012, ["Drama", "Adventure", "Crime"], 165, 78, 8.4, 15000, ["Netflix"], ["Jamie Foxx", "Christoph Waltz"], "Quentin Tarantino", "Weinstein", ["western", "slavery", "revenge", "bounty"], "A freed slave sets out to rescue his wife from a plantation owner."),
    ("Inglourious Basterds", 2009, ["Drama", "Adventure", "Thriller"], 153, 77, 8.3, 14000, ["Netflix"], ["Brad Pitt", "Christoph Waltz"], "Quentin Tarantino", "Weinstein", ["war", "nazi", "revenge", "alt-history"], "A plan to assassinate Nazi leaders in occupied France."),
    ("Heat", 1995, ["Crime", "Drama", "Action"], 170, 70, 8.3, 9000, ["Prime Video"], ["Al Pacino", "Robert De Niro"], "Michael Mann", "Warner Bros", ["heist", "cops", "obsession", "la"], "A detective pursues a skilled crew of armed robbers."),
    ("Se7en", 1995, ["Crime", "Thriller", "Drama"], 127, 75, 8.6, 16000, ["Netflix"], ["Brad Pitt", "Morgan Freeman"], "David Fincher", "New Line", ["serial-killer", "sins", "noir", "detective"], "Two detectives hunt a killer using the seven deadly sins as motives."),
    ("The Departed", 2006, ["Crime", "Drama", "Thriller"], 151, 76, 8.5, 14000, ["Max"], ["Leonardo DiCaprio", "Matt Damon"], "Martin Scorsese", "Warner Bros", ["mob", "undercover", "boston", "betrayal"], "An undercover cop and a mole try to identify each other."),
    ("Casino Royale", 2006, ["Action", "Adventure", "Thriller"], 144, 74, 8.0, 10000, ["Prime Video"], ["Daniel Craig", "Eva Green"], "Martin Campbell", "Sony", ["spy", "bond", "poker", "espionage"], "James Bond's first mission as 007 takes him to a high-stakes poker game."),
    ("Logan", 2017, ["Action", "Drama", "Sci-Fi"], 137, 80, 8.1, 12000, ["Disney+"], ["Hugh Jackman"], "James Mangold", "Fox", ["mutant", "aging", "roadtrip", "western"], "An aging Wolverine cares for an ailing Professor X in a bleak future."),
    ("Spider-Man: Into the Spider-Verse", 2018, ["Animation", "Action", "Adventure"], 117, 86, 8.4, 13000, ["Netflix"], ["Shameik Moore"], "Bob Persichetti", "Sony Animation", ["multiverse", "hero", "animation", "coming-of-age"], "Teen Miles Morales becomes Spider-Man across the multiverse."),
    ("Top Gun: Maverick", 2022, ["Action", "Drama", "Adventure"], 130, 88, 8.2, 12000, ["Paramount", "Prime Video"], ["Tom Cruise"], "Joseph Kosinski", "Paramount", ["fighter-jet", "mentor", "redemption", "navy"], "Maverick trains a new squad for a dangerous mission."),
    ("The Batman", 2022, ["Action", "Crime", "Drama"], 176, 85, 7.8, 11000, ["Max"], ["Robert Pattinson", "Zoë Kravitz"], "Matt Reeves", "Warner Bros", ["batman", "noir", "riddler", "gotham"], "Batman investigates a sadistic killer leaving cryptic clues."),
    ("Tenet", 2020, ["Sci-Fi", "Action", "Thriller"], 150, 76, 7.3, 9000, ["Max"], ["John David Washington"], "Christopher Nolan", "Warner Bros", ["time", "inversion", "spy", "physics"], "A secret agent manipulates the flow of time to prevent WWIII."),
    ("Dunkirk", 2017, ["Drama", "Thriller", "Action"], 106, 74, 7.8, 9000, ["Max"], ["Fionn Whitehead"], "Christopher Nolan", "Warner Bros", ["war", "survival", "evacuation", "wwii"], "Allied soldiers are evacuated during a fierce WWII battle."),
    ("1917", 2019, ["Drama", "Thriller", "Action"], 119, 77, 8.2, 10000, ["Prime Video"], ["George MacKay"], "Sam Mendes", "Universal", ["war", "one-shot", "mission", "wwi"], "Two soldiers race to deliver a message that could save 1,600 men."),
    ("Hereditary", 2018, ["Horror", "Drama", "Thriller"], 127, 72, 7.3, 8000, ["Max"], ["Toni Collette"], "Ari Aster", "A24", ["grief", "cult", "family", "dread"], "A family unravels terrifying secrets after the grandmother's death."),
    ("Midsommar", 2019, ["Horror", "Drama", "Thriller"], 148, 70, 7.1, 7500, ["Prime Video"], ["Florence Pugh"], "Ari Aster", "A24", ["cult", "folk", "grief", "ritual"], "A grieving woman joins her boyfriend at a disturbing Swedish festival."),
    ("A Quiet Place", 2018, ["Horror", "Thriller", "Sci-Fi"], 90, 78, 7.5, 9000, ["Paramount", "Prime Video"], ["Emily Blunt", "John Krasinski"], "John Krasinski", "Paramount", ["silence", "monster", "family", "survival"], "A family survives in silence to avoid creatures that hunt by sound."),
    ("The Grand Heist", 2021, ["Crime", "Thriller", "Action"], 118, 65, 6.9, 4000, ["Netflix"], ["Ensemble Cast"], "Indie Director", "Indie Studio", ["heist", "crew", "twist", "money"], "A meticulous crew plans the heist of a lifetime."),
    ("Northern Lights", 2020, ["Romance", "Drama"], 102, 60, 6.7, 3000, ["Prime Video"], ["Ensemble Cast"], "Indie Director", "Indie Studio", ["love", "winter", "journey", "emotional"], "Two strangers fall in love during a road trip to see the aurora."),
    ("Deep Current", 2023, ["Documentary", "Drama"], 95, 58, 7.0, 2500, ["Disney+"], ["Narrator"], "Doc Director", "Nat Studios", ["ocean", "nature", "climate", "wildlife"], "An immersive dive into the secret life of the deep ocean."),
]

SERIES = [
    ("Breaking Bad", 2008, ["Crime", "Drama", "Thriller"], 49, 94, 9.5, 18000, ["Netflix"], ["Bryan Cranston", "Aaron Paul"], "Vince Gilligan", "Sony", ["meth", "transformation", "crime", "antihero"], "A chemistry teacher turns to manufacturing drugs after a cancer diagnosis."),
    ("Better Call Saul", 2015, ["Crime", "Drama"], 46, 85, 9.0, 9000, ["Netflix"], ["Bob Odenkirk"], "Vince Gilligan", "Sony", ["lawyer", "prequel", "crime", "morality"], "The transformation of con artist Jimmy McGill into lawyer Saul Goodman."),
    ("The Sopranos", 1999, ["Crime", "Drama"], 55, 80, 9.2, 11000, ["Max"], ["James Gandolfini"], "David Chase", "HBO", ["mafia", "therapy", "family", "power"], "A New Jersey mob boss balances family life and organized crime."),
    ("The Wire", 2002, ["Crime", "Drama", "Thriller"], 59, 78, 9.3, 9000, ["Max"], ["Dominic West"], "David Simon", "HBO", ["police", "drugs", "city", "institutions"], "The Baltimore drug scene seen through eyes of dealers and police."),
    ("Game of Thrones", 2011, ["Fantasy", "Drama", "Adventure"], 57, 95, 9.2, 22000, ["Max"], ["Emilia Clarke", "Kit Harington"], "David Benioff", "HBO", ["dragons", "power", "war", "politics"], "Noble families vie for control of the Iron Throne of Westeros."),
    ("Stranger Things", 2016, ["Sci-Fi", "Horror", "Drama"], 51, 96, 8.7, 20000, ["Netflix"], ["Millie Bobby Brown"], "The Duffer Brothers", "Netflix", ["80s", "monster", "kids", "supernatural"], "Kids in a small town uncover supernatural mysteries and government secrets."),
    ("Dark", 2017, ["Sci-Fi", "Thriller", "Drama"], 60, 86, 8.7, 9000, ["Netflix"], ["Louis Hofmann"], "Baran bo Odar", "Netflix", ["time-travel", "mystery", "german", "loops"], "Four families search for the truth behind a child's disappearance across time."),
    ("Severance", 2022, ["Sci-Fi", "Thriller", "Drama"], 50, 89, 8.7, 8000, ["Apple TV+"], ["Adam Scott"], "Dan Erickson", "Apple", ["work", "memory", "dystopia", "mystery"], "Employees surgically divide their work and personal memories."),
    ("Black Mirror", 2011, ["Sci-Fi", "Thriller", "Drama"], 60, 84, 8.7, 10000, ["Netflix"], ["Anthology Cast"], "Charlie Brooker", "Netflix", ["technology", "dystopia", "anthology", "future"], "An anthology exploring the dark side of technology."),
    ("Chernobyl", 2019, ["Drama", "Thriller", "Documentary"], 67, 88, 9.4, 9000, ["Max"], ["Jared Harris"], "Craig Mazin", "HBO", ["disaster", "history", "nuclear", "truth"], "A dramatization of the 1986 nuclear disaster and its aftermath."),
    ("True Detective", 2014, ["Crime", "Drama", "Thriller"], 55, 82, 8.9, 9000, ["Max"], ["Matthew McConaughey"], "Nic Pizzolatto", "HBO", ["detective", "anthology", "dark", "philosophy"], "Detectives investigate haunting cases across time."),
    ("Fargo", 2014, ["Crime", "Drama", "Thriller"], 53, 80, 8.9, 8000, ["Prime Video"], ["Anthology Cast"], "Noah Hawley", "FX", ["crime", "anthology", "dark-comedy", "midwest"], "Anthology of crime stories set in the upper Midwest."),
    ("Mindhunter", 2017, ["Crime", "Drama", "Thriller"], 50, 78, 8.6, 7000, ["Netflix"], ["Jonathan Groff"], "Joe Penhall", "Netflix", ["serial-killer", "fbi", "psychology", "profiling"], "FBI agents interview imprisoned serial killers to solve ongoing cases."),
    ("Westworld", 2016, ["Sci-Fi", "Drama", "Thriller"], 62, 79, 8.5, 9000, ["Max"], ["Evan Rachel Wood"], "Jonathan Nolan", "HBO", ["ai", "robots", "consciousness", "western"], "A futuristic theme park populated by lifelike android hosts."),
    ("The Mandalorian", 2019, ["Sci-Fi", "Adventure", "Action"], 40, 87, 8.6, 10000, ["Disney+"], ["Pedro Pascal"], "Jon Favreau", "Lucasfilm", ["star-wars", "bounty-hunter", "space", "western"], "A lone bounty hunter protects a mysterious child across the galaxy."),
    ("The Last of Us", 2023, ["Drama", "Horror", "Adventure"], 55, 91, 8.7, 11000, ["Max"], ["Pedro Pascal", "Bella Ramsey"], "Craig Mazin", "HBO", ["apocalypse", "infection", "survival", "bond"], "A smuggler escorts a teenage girl across a post-apocalyptic America."),
    ("Succession", 2018, ["Drama", "Comedy"], 60, 84, 8.9, 8000, ["Max"], ["Brian Cox"], "Jesse Armstrong", "HBO", ["power", "family", "media", "wealth"], "A media dynasty fights for control as the patriarch's health declines."),
    ("The Crown", 2016, ["Drama", "Documentary"], 58, 80, 8.6, 8000, ["Netflix"], ["Claire Foy"], "Peter Morgan", "Netflix", ["royalty", "history", "politics", "britain"], "The reign of Queen Elizabeth II from the 1940s onward."),
    ("Peaky Blinders", 2013, ["Crime", "Drama"], 58, 86, 8.8, 10000, ["Netflix"], ["Cillian Murphy"], "Steven Knight", "BBC", ["gangster", "1920s", "family", "britain"], "A gangster family rises to power in 1920s Birmingham."),
    ("Narcos", 2015, ["Crime", "Drama", "Thriller"], 49, 82, 8.8, 9000, ["Netflix"], ["Wagner Moura"], "Chris Brancato", "Netflix", ["cartel", "drugs", "colombia", "dea"], "The rise and fall of the Medellín drug cartel."),
    ("Ozark", 2017, ["Crime", "Drama", "Thriller"], 56, 81, 8.5, 9000, ["Netflix"], ["Jason Bateman"], "Bill Dubuque", "Netflix", ["money-laundering", "cartel", "family", "crime"], "A financial planner launders money for a cartel in the Ozarks."),
    ("Sherlock", 2010, ["Crime", "Drama", "Thriller"], 88, 84, 9.0, 11000, ["Netflix"], ["Benedict Cumberbatch"], "Steven Moffat", "BBC", ["detective", "modern", "mystery", "deduction"], "A modern update of Sherlock Holmes solving crimes in London."),
    ("The Boys", 2019, ["Action", "Comedy", "Crime"], 60, 89, 8.7, 11000, ["Prime Video"], ["Karl Urban"], "Eric Kripke", "Amazon", ["superhero", "satire", "violence", "corruption"], "Vigilantes take on corrupt superheroes who abuse their powers."),
    ("Fleabag", 2016, ["Comedy", "Drama"], 27, 78, 8.7, 6000, ["Prime Video"], ["Phoebe Waller-Bridge"], "Phoebe Waller-Bridge", "BBC", ["dark-comedy", "grief", "love", "british"], "A witty woman navigates life and love in London."),
    ("Ted Lasso", 2020, ["Comedy", "Drama"], 30, 85, 8.8, 8000, ["Apple TV+"], ["Jason Sudeikis"], "Bill Lawrence", "Apple", ["football", "optimism", "feel-good", "team"], "An American coach takes charge of a struggling English football team."),
    ("The Office", 2005, ["Comedy"], 22, 88, 9.0, 12000, ["Peacock", "Prime Video"], ["Steve Carell"], "Greg Daniels", "NBC", ["workplace", "mockumentary", "comedy", "ensemble"], "The daily lives of office employees at a paper company."),
    ("Friends", 1994, ["Comedy", "Romance"], 22, 86, 8.9, 11000, ["Max"], ["Jennifer Aniston"], "David Crane", "NBC", ["friendship", "sitcom", "new-york", "love"], "Six friends navigate life and love in New York City."),
    ("Rick and Morty", 2013, ["Animation", "Comedy", "Sci-Fi"], 23, 87, 9.1, 12000, ["Max"], ["Justin Roiland"], "Dan Harmon", "Adult Swim", ["multiverse", "sci-fi", "dark-comedy", "adventure"], "A genius scientist drags his grandson on interdimensional adventures."),
    ("House M.D.", 2004, ["Drama", "Crime"], 44, 82, 8.7, 9000, ["Prime Video"], ["Hugh Laurie"], "David Shore", "Fox", ["medical", "genius", "mystery", "diagnosis"], "A brilliant but misanthropic doctor solves baffling medical cases."),
    ("Mr. Robot", 2015, ["Drama", "Crime", "Thriller"], 49, 79, 8.5, 8000, ["Prime Video"], ["Rami Malek"], "Sam Esmail", "USA", ["hacker", "revolution", "tech", "identity"], "A cybersecurity engineer is recruited by an anarchist hacker group."),
]

ANIME = [
    ("Attack on Titan", 2013, ["Action", "Drama", "Fantasy"], 24, 96, 9.1, 16000, ["Crunchyroll"], ["Yuki Kaji"], "Hajime Isayama", "Wit Studio", ["titans", "survival", "war", "freedom"], "Humanity fights for survival against man-eating giants."),
    ("Death Note", 2006, ["Thriller", "Crime", "Fantasy"], 24, 92, 9.0, 14000, ["Netflix", "Crunchyroll"], ["Mamoru Miyano"], "Tsugumi Ohba", "Madhouse", ["notebook", "death", "detective", "morality"], "A student gains a notebook that kills anyone whose name is written in it."),
    ("Fullmetal Alchemist: Brotherhood", 2009, ["Action", "Adventure", "Fantasy"], 24, 90, 9.2, 13000, ["Crunchyroll"], ["Romi Park"], "Hiromu Arakawa", "Bones", ["alchemy", "brothers", "war", "philosophy"], "Two brothers use alchemy in search of the Philosopher's Stone."),
    ("Steins;Gate", 2011, ["Sci-Fi", "Thriller", "Drama"], 24, 84, 9.0, 9000, ["Crunchyroll"], ["Mamoru Miyano"], "Chiyomaru Shikura", "White Fox", ["time-travel", "science", "conspiracy", "drama"], "A self-proclaimed mad scientist discovers a way to send messages to the past."),
    ("Cowboy Bebop", 1998, ["Sci-Fi", "Action", "Adventure"], 24, 82, 8.9, 9000, ["Crunchyroll", "Netflix"], ["Koichi Yamadera"], "Shinichiro Watanabe", "Sunrise", ["bounty-hunter", "space", "jazz", "noir"], "A ragtag crew of bounty hunters chases criminals across the solar system."),
    ("Jujutsu Kaisen", 2020, ["Action", "Fantasy", "Horror"], 24, 95, 8.6, 12000, ["Crunchyroll"], ["Junya Enoki"], "Gege Akutami", "MAPPA", ["curses", "sorcery", "school", "battle"], "A boy joins a school of sorcerers to fight deadly curses."),
    ("Demon Slayer", 2019, ["Action", "Fantasy", "Adventure"], 24, 96, 8.7, 13000, ["Crunchyroll", "Netflix"], ["Natsuki Hanae"], "Koyoharu Gotouge", "Ufotable", ["demons", "swordsman", "family", "revenge"], "A young boy becomes a demon slayer to save his sister."),
    ("One Piece", 1999, ["Adventure", "Action", "Comedy"], 24, 93, 8.9, 14000, ["Crunchyroll", "Netflix"], ["Mayumi Tanaka"], "Eiichiro Oda", "Toei", ["pirates", "treasure", "friendship", "adventure"], "A young pirate searches for the ultimate treasure, the One Piece."),
    ("Naruto", 2002, ["Action", "Adventure", "Fantasy"], 23, 90, 8.4, 12000, ["Crunchyroll"], ["Junko Takeuchi"], "Masashi Kishimoto", "Pierrot", ["ninja", "friendship", "growth", "village"], "A young ninja seeks recognition and dreams of becoming his village's leader."),
    ("Hunter x Hunter", 2011, ["Adventure", "Action", "Fantasy"], 24, 88, 9.0, 11000, ["Crunchyroll", "Netflix"], ["Megumi Han"], "Yoshihiro Togashi", "Madhouse", ["hunter", "adventure", "friendship", "power"], "A boy becomes a Hunter to find his absent father."),
    ("Code Geass", 2006, ["Sci-Fi", "Action", "Drama"], 24, 84, 8.7, 9000, ["Crunchyroll"], ["Jun Fukuyama"], "Goro Taniguchi", "Sunrise", ["mecha", "rebellion", "strategy", "power"], "An exiled prince gains a power that lets him command anyone."),
    ("Vinland Saga", 2019, ["Action", "Adventure", "Drama"], 24, 83, 8.8, 8000, ["Netflix", "Crunchyroll"], ["Yuto Uemura"], "Makoto Yukimura", "Wit Studio", ["vikings", "revenge", "war", "history"], "A young warrior seeks revenge in the brutal age of Vikings."),
    ("Chainsaw Man", 2022, ["Action", "Horror", "Fantasy"], 24, 90, 8.5, 9000, ["Crunchyroll"], ["Kikunosuke Toya"], "Tatsuki Fujimoto", "MAPPA", ["devils", "chaos", "hunter", "dark"], "A young man merges with a chainsaw devil to hunt other devils."),
    ("Spy x Family", 2022, ["Comedy", "Action", "Adventure"], 24, 89, 8.5, 9000, ["Crunchyroll"], ["Takuya Eguchi"], "Tatsuya Endo", "Wit Studio", ["spy", "family", "comedy", "wholesome"], "A spy builds a fake family, unaware they each hide secrets."),
    ("Mob Psycho 100", 2016, ["Action", "Comedy", "Fantasy"], 24, 82, 8.7, 8000, ["Crunchyroll"], ["Setsuo Ito"], "ONE", "Bones", ["psychic", "coming-of-age", "comedy", "growth"], "A powerful young psychic tries to live a normal life."),
    ("Re:Zero", 2016, ["Fantasy", "Drama", "Thriller"], 24, 84, 8.4, 8000, ["Crunchyroll"], ["Yusuke Kobayashi"], "Tappei Nagatsuki", "White Fox", ["isekai", "time-loop", "fantasy", "suffering"], "A young man is transported to another world where he can return from death."),
    ("Your Lie in April", 2014, ["Drama", "Romance"], 23, 80, 8.6, 7000, ["Crunchyroll", "Netflix"], ["Natsuki Hanae"], "Naoshi Arakawa", "A-1 Pictures", ["music", "love", "grief", "emotional"], "A piano prodigy rediscovers music through a free-spirited violinist."),
    ("Violet Evergarden", 2018, ["Drama", "Fantasy", "Romance"], 24, 83, 8.7, 7000, ["Netflix"], ["Yui Ishikawa"], "Kana Akatsuki", "Kyoto Animation", ["emotion", "war", "letters", "healing"], "A former soldier becomes a ghostwriter to understand human emotion."),
    ("Made in Abyss", 2017, ["Adventure", "Fantasy", "Drama"], 24, 78, 8.3, 6000, ["Prime Video", "Crunchyroll"], ["Miyu Tomita"], "Akihito Tsukushi", "Kinema Citrus", ["abyss", "exploration", "dark", "mystery"], "A girl and a robot descend into a mysterious, deadly chasm."),
    ("Monster", 2004, ["Thriller", "Crime", "Drama"], 24, 80, 8.9, 7000, ["Netflix"], ["Hidenobu Kiuchi"], "Naoki Urasawa", "Madhouse", ["serial-killer", "doctor", "psychology", "chase"], "A surgeon hunts a former patient who became a serial killer."),
    ("Berserk", 1997, ["Action", "Adventure", "Horror"], 24, 76, 8.7, 6000, ["Crunchyroll"], ["Nobutoshi Canna"], "Kentaro Miura", "OLM", ["dark-fantasy", "war", "revenge", "demons"], "A lone mercenary battles demonic forces in a dark medieval world."),
    ("Tokyo Ghoul", 2014, ["Action", "Horror", "Drama"], 24, 84, 7.8, 8000, ["Crunchyroll", "Prime Video"], ["Natsuki Hanae"], "Sui Ishida", "Pierrot", ["ghoul", "identity", "dark", "survival"], "A student becomes a half-ghoul and struggles to live between two worlds."),
    ("My Hero Academia", 2016, ["Action", "Adventure", "Fantasy"], 24, 90, 8.3, 11000, ["Crunchyroll"], ["Daiki Yamashita"], "Kohei Horikoshi", "Bones", ["superhero", "school", "powers", "growth"], "A powerless boy enrolls in a hero academy to become the greatest hero."),
    ("Bleach", 2004, ["Action", "Adventure", "Fantasy"], 24, 85, 8.2, 9000, ["Crunchyroll", "Disney+"], ["Masakazu Morita"], "Tite Kubo", "Pierrot", ["soul-reaper", "spirits", "battle", "swords"], "A teenager gains the powers of a soul reaper to protect the living."),
    ("Dragon Ball Z", 1989, ["Action", "Adventure", "Fantasy"], 24, 86, 8.2, 9000, ["Crunchyroll"], ["Masako Nozawa"], "Akira Toriyama", "Toei", ["martial-arts", "aliens", "power", "tournament"], "Goku defends Earth against powerful villains."),
    ("Neon Genesis Evangelion", 1995, ["Sci-Fi", "Drama", "Action"], 24, 80, 8.5, 7000, ["Netflix"], ["Megumi Ogata"], "Hideaki Anno", "Gainax", ["mecha", "angels", "psychology", "apocalypse"], "Teenagers pilot giant bio-machines to fight mysterious beings."),
    ("Cyberpunk: Edgerunners", 2022, ["Sci-Fi", "Action", "Drama"], 25, 88, 8.6, 8000, ["Netflix"], ["Zach Aguilar"], "CD Projekt", "Trigger", ["cyberpunk", "future", "crime", "tragedy"], "A street kid becomes a mercenary in a dystopian future city."),
    ("Frieren: Beyond Journey's End", 2023, ["Adventure", "Fantasy", "Drama"], 24, 92, 9.0, 9000, ["Crunchyroll"], ["Atsumi Tanezaki"], "Kanehito Yamada", "Madhouse", ["elf", "journey", "memory", "emotional"], "An immortal elf mage reflects on her past companions on a new journey."),
    ("Vivy: Fluorite Eye's Song", 2021, ["Sci-Fi", "Action", "Drama"], 24, 78, 8.4, 5000, ["Crunchyroll"], ["Kairi Yagi"], "Tappei Nagatsuki", "Wit Studio", ["ai", "music", "future", "time-travel"], "An autonomous AI fights to prevent a war between humans and machines."),
    ("Erased", 2016, ["Thriller", "Drama", "Fantasy"], 23, 82, 8.4, 6000, ["Crunchyroll", "Netflix"], ["Shinnosuke Mitsushima"], "Kei Sanbe", "A-1 Pictures", ["time-travel", "mystery", "childhood", "redemption"], "A man travels back in time to prevent a series of childhood kidnappings."),
]


def _build(row, ctype):
    (title, year, genres, runtime, pop, rating, votes, providers,
     cast, crew, studio, keywords, overview) = row
    return {
        "id": str(uuid.uuid4()),
        "source": "seed",
        "source_id": _slug(title),
        "type": ctype,
        "title": title,
        "original_title": title,
        "year": year,
        "overview": overview,
        "poster_url": _poster(title),
        "backdrop_url": _backdrop(title),
        "runtime": runtime,
        "status": "released",
        "genres": genres,
        "keywords": keywords,
        "cast": cast,
        "crew": [crew],
        "creator": crew,
        "studios": [studio],
        "countries": ["JP"] if ctype == "anime" else ["US"],
        "languages": ["ja"] if ctype == "anime" else ["en"],
        "external_rating": rating,
        "vote_count": votes,
        "popularity": pop,
        "trailer_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "providers": providers,
        "seasons": (random.randint(1, 5) if ctype != "movie" else 0),
        "episodes": (random.randint(10, 60) if ctype != "movie" else 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_catalog():
    catalog = []
    for r in MOVIES:
        catalog.append(_build(r, "movie"))
    for r in SERIES:
        catalog.append(_build(r, "series"))
    for r in ANIME:
        catalog.append(_build(r, "anime"))
    return catalog
