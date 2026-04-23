import os
import re
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
# A customizable profanity filter that replaces inappropriate words with censored versions. The filter loads a list of banned words from a default file and allows for additional custom words to be added. It provides methods to add or remove words from the banned list, save the current list to a file, and censor text by replacing profane words with a specified replacement string or asterisks based on word length. The filter also includes a method to check if a given text contains any profanity.
class ProfanityFilter:
    """
    A customizable profanity filter that replaces inappropriate words with censored versions.
    """
    def __init__(self, replacement="****", custom_words_file=None):
        """
        Initialize the profanity filter.
        
        Args:
            replacement (str): The string to replace profane words with
            custom_words_file (str): Path to a custom file containing banned words
        """
        self.replacement = replacement
        self.banned_words = set()
        
        # Load default banned words
        try:
            with open('banned_words.txt', 'r') as f:
                for line in f:
                    word = line.strip()
                    if word and not word.startswith('#'):
                        self.banned_words.add(word.lower())
            logger.debug(f"Loaded {len(self.banned_words)} banned words from default file")
        except FileNotFoundError:
            logger.warning("Default banned words file not found. Creating empty set.")
            # If the file doesn't exist, we'll use an empty set for now
            
        # Load custom banned words if provided
        if custom_words_file and os.path.exists(custom_words_file):
            try:
                with open(custom_words_file, 'r') as f:
                    for line in f:
                        word = line.strip()
                        if word and not word.startswith('#'):
                            self.banned_words.add(word.lower())
                logger.debug(f"Loaded additional words from custom file: {custom_words_file}")
            except Exception as e:
                logger.error(f"Error loading custom banned words file: {e}")
    # Add a word to the banned words list. The word is converted to lowercase to ensure case-insensitive matching.
    def add_word(self, word):
        """Add a word to the banned words list."""
        self.banned_words.add(word.lower())
    # Remove a word from the banned words list. The word is converted to lowercase to ensure case-insensitive matching before removal.
    def remove_word(self, word):
        """Remove a word from the banned words list."""
        if word.lower() in self.banned_words:
            self.banned_words.remove(word.lower())
    # Save the current list of banned words to a file. The words are saved in sorted order, and a comment is included at the top of the file for clarity. If an error occurs during saving, it is logged and the function returns False; otherwise, it returns True upon successful saving.
    def save_banned_words(self, filepath='banned_words.txt'):
        """Save the current list of banned words to a file."""
        try:
            with open(filepath, 'w') as f:
                f.write("# List of banned words for profanity filtering\n")
                for word in sorted(self.banned_words):
                    f.write(f"{word}\n")
            logger.debug(f"Saved {len(self.banned_words)} banned words to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error saving banned words: {e}")
            return False
    # Generate a regex pattern that matches any of the banned words with word boundaries. This ensures that only whole words are matched and not substrings within other words. The pattern is compiled with the IGNORECASE flag to allow for case-insensitive matching.
    def _get_word_boundaries_pattern(self):
        """Get a regex pattern with word boundaries for all banned words."""
        if not self.banned_words:
            return None
        
        # Escape special regex characters in the banned words
        escaped_words = [re.escape(word) for word in self.banned_words]
        
        # Create a pattern that matches whole words only (with word boundaries)
        pattern = r'\b(' + '|'.join(escaped_words) + r')\b'
        return re.compile(pattern, re.IGNORECASE)
    # Censor profanity in the given text. The method uses the generated regex pattern to find and replace any profane words in the input text. The replacement can either be a fixed string (like "****") or a string of asterisks that matches the length of the profane word, depending on the configuration. If there are no banned words or if the input text is empty, the original text is returned unchanged.
    def censor(self, text):
        """
        Censor profanity in the given text.
        
        Args:
            text (str): The text to censor
            
        Returns:
            str: The censored text
        """
        if not text or not self.banned_words:
            return text
            
        pattern = self._get_word_boundaries_pattern()
        if not pattern:
            return text
            
        # Function to replace matched words with the appropriate number of * characters
        def replace_match(match):
            matched_word = match.group(0)
            # Use either the configured replacement or generate stars based on word length
            if self.replacement == "****":
                return '*' * len(matched_word)
            return self.replacement
            
        return pattern.sub(replace_match, text)
    
    def contains_profanity(self, text):
        """
        Check if the text contains any profanity.
        
        Args:
            text (str): The text to check
            
        Returns:
            bool: True if profanity is found, False otherwise
        """
        if not text or not self.banned_words:
            return False
            
        pattern = self._get_word_boundaries_pattern()
        if not pattern:
            return False
            
        return bool(pattern.search(text))
