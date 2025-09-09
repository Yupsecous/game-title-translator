# statistics_handler.py
import os
import re
import time
from datetime import datetime
from logger import log_debug

class StatisticsHandler:
    """Handles parsing API usage logs and calculating statistics for cost monitoring."""
    
    def __init__(self, app):
        self.app = app
        
        # Use the same base directory pattern as other app components
        import sys
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.ocr_log_file = os.path.join(base_dir, "GEMINI_API_OCR_short_log.txt")
        self.translation_log_file = os.path.join(base_dir, "GEMINI_API_TRA_short_log.txt")
        self.openai_translation_log_file = os.path.join(base_dir, "OpenAI_API_TRA_short_log.txt")
        
        log_debug(f"Statistics handler initialized - OCR log: {self.ocr_log_file}, Translation log: {self.translation_log_file}, OpenAI log: {self.openai_translation_log_file}")
        
        # Cache for parsed data to avoid re-parsing
        self._cache_timestamp = 0
        self._cached_stats = None
    
    def parse_log_file(self, file_path):
        """Parse a short log file and extract session data."""
        if not os.path.exists(file_path):
            log_debug(f"Log file not found: {file_path}")
            return []
        
        sessions = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split by sessions
            session_blocks = re.split(r'SESSION \d+ STARTED', content)
            
            for block in session_blocks[1:]:  # Skip first empty split
                session_data = self._parse_session_block(block)
                if session_data:
                    sessions.append(session_data)
                    
        except Exception as e:
            log_debug(f"Error parsing log file {file_path}: {e}")
        
        log_debug(f"Parsed {len(sessions)} sessions from {os.path.basename(file_path)}")
        return sessions
    
    def _parse_session_block(self, block):
        """Parse a single session block and extract calls data."""
        try:
            # Extract session start time
            start_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)', block)
            if not start_match:
                return None
            
            session_start = start_match.group(1)
            
            # Extract session end time
            end_match = re.search(r'SESSION \d+ ENDED (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)', block)
            if not end_match:
                return None
            
            session_end = end_match.group(1)
            
            # Calculate session duration
            try:
                start_time = datetime.strptime(session_start, "%Y-%m-%d %H:%M:%S.%f")
                end_time = datetime.strptime(session_end, "%Y-%m-%d %H:%M:%S.%f")
                duration_seconds = (end_time - start_time).total_seconds()
            except ValueError:
                duration_seconds = 0
            
            # Extract all API calls in this session
            calls = []
            
            # For OCR calls
            ocr_calls = re.finditer(r'========= OCR CALL ===========.*?Result:\s*-+\s*(.*?)\s*-+', block, re.DOTALL)
            for call_match in ocr_calls:
                call_data = self._parse_call_data(call_match.group(0))
                if call_data:
                    call_data['type'] = 'ocr'
                    calls.append(call_data)
            
            # For Translation calls
            trans_calls = re.finditer(r'===== TRANSLATION CALL =======.*?Result:\s*-+\s*(.*?)\s*-+', block, re.DOTALL)
            for call_match in trans_calls:
                call_data = self._parse_call_data(call_match.group(0))
                if call_data:
                    call_data['type'] = 'translation'
                    # Extract word count from translation calls
                    result_text = call_match.group(1)
                    call_data['word_count'] = self._count_words_in_translation(result_text)
                    calls.append(call_data)
            
            return {
                'start_time': session_start,
                'end_time': session_end,
                'duration_seconds': duration_seconds,
                'calls': calls
            }
            
        except Exception as e:
            log_debug(f"Error parsing session block: {e}")
            return None
    
    def _parse_call_data(self, call_text):
        """Parse individual call data from call block."""
        try:
            # Extract duration
            duration_match = re.search(r'Duration: ([\d\.]+)s', call_text)
            duration = float(duration_match.group(1)) if duration_match else 0.0
            
            # Extract cost
            cost_match = re.search(r'Cost: \$([0-9\.]+)', call_text)
            cost = float(cost_match.group(1)) if cost_match else 0.0
            
            return {
                'duration': duration,
                'cost': cost
            }
        except Exception as e:
            log_debug(f"Error parsing call data: {e}")
            return None
    
    def _count_words_in_translation(self, result_text):
        """Count words in translation result text."""
        try:
            # Look for target language text (after arrow or second line)
            lines = result_text.strip().split('\n')
            
            # Find target text (usually after ENGLISH: or POLISH: etc.)
            target_text = ""
            for line in lines:
                if ':' in line and len(line.split(':', 1)) > 1:
                    potential_target = line.split(':', 1)[1].strip()
                    if potential_target and potential_target != '<EMPTY>':
                        target_text = potential_target
                        break
            
            if not target_text:
                return 0
            
            # Simple word count
            words = target_text.split()
            return len(words)
            
        except Exception as e:
            log_debug(f"Error counting words: {e}")
            return 0
    
    def get_statistics(self):
        """Get comprehensive API usage statistics."""
        # Check if we need to refresh cache
        current_time = time.time()
        if self._cached_stats and (current_time - self._cache_timestamp) < 5.0:
            return self._cached_stats
        
        try:
            # Parse both log files
            ocr_sessions = self.parse_log_file(self.ocr_log_file)
            translation_sessions = self.parse_log_file(self.translation_log_file)
            openai_translation_sessions = self.parse_log_file(self.openai_translation_log_file)
            
            # Calculate OCR statistics
            ocr_stats = self._calculate_ocr_statistics(ocr_sessions)
            
            # Calculate translation statistics
            translation_stats = self._calculate_translation_statistics(translation_sessions)
            
            # Calculate OpenAI translation statistics
            openai_translation_stats = self._calculate_translation_statistics(openai_translation_sessions)
            
            # Calculate combined statistics
            combined_stats = self._calculate_combined_statistics(ocr_stats, translation_stats)
            
            stats = {
                'ocr': ocr_stats,
                'translation': translation_stats,
                'openai_translation': openai_translation_stats,
                'combined': combined_stats
            }
            
            # Update cache
            self._cached_stats = stats
            self._cache_timestamp = current_time
            
            return stats
            
        except Exception as e:
            log_debug(f"Error calculating statistics: {e}")
            return self._get_empty_statistics()
    
    def _calculate_ocr_statistics(self, sessions):
        """Calculate OCR-specific statistics."""
        total_cost = 0.0
        total_calls = 0
        total_duration = 0.0
        call_durations = []  # List to store all individual call durations
        
        for session in sessions:
            for call in session['calls']:
                if call.get('type') == 'ocr':
                    total_cost += call.get('cost', 0.0)
                    total_calls += 1
                    duration = call.get('duration', 0.0)
                    call_durations.append(duration)
            total_duration += session.get('duration_seconds', 0.0)
        
        # Calculate median duration
        median_duration = 0.0
        if call_durations:
            call_durations.sort()
            n = len(call_durations)
            if n % 2 == 0:
                # Even number of calls - average of two middle values
                median_duration = (call_durations[n//2 - 1] + call_durations[n//2]) / 2.0
            else:
                # Odd number of calls - middle value
                median_duration = call_durations[n//2]
        
        # Calculate derived statistics - ensure per-hour uses exact per-minute calculation with proper rounding
        avg_cost_per_call = total_cost / total_calls if total_calls > 0 else 0.0
        avg_cost_per_minute = (total_cost / (total_duration / 60.0)) if total_duration > 0 else 0.0
        # Round cost per minute to 8 decimal places, then multiply by 60 for consistency
        avg_cost_per_minute_rounded = round(avg_cost_per_minute, 8)
        avg_cost_per_hour = avg_cost_per_minute_rounded * 60.0
        
        return {
            'total_cost': total_cost,
            'total_calls': total_calls,
            'median_duration': median_duration,
            'avg_cost_per_call': avg_cost_per_call,
            'avg_cost_per_minute': avg_cost_per_minute,
            'avg_cost_per_hour': avg_cost_per_hour,
            'total_duration_seconds': total_duration
        }
    
    def _calculate_translation_statistics(self, sessions):
        """Calculate translation-specific statistics."""
        total_cost = 0.0
        total_calls = 0
        total_words = 0
        total_duration = 0.0
        call_durations = []  # List to store all individual call durations
        
        for session in sessions:
            for call in session['calls']:
                if call.get('type') == 'translation':
                    total_cost += call.get('cost', 0.0)
                    total_calls += 1
                    total_words += call.get('word_count', 0)
                    duration = call.get('duration', 0.0)
                    call_durations.append(duration)
            total_duration += session.get('duration_seconds', 0.0)
        
        # Calculate median duration
        median_duration = 0.0
        if call_durations:
            call_durations.sort()
            n = len(call_durations)
            if n % 2 == 0:
                # Even number of calls - average of two middle values
                median_duration = (call_durations[n//2 - 1] + call_durations[n//2]) / 2.0
            else:
                # Odd number of calls - middle value
                median_duration = call_durations[n//2]
        
        # Calculate derived statistics
        avg_cost_per_word = total_cost / total_words if total_words > 0 else 0.0
        avg_cost_per_call = total_cost / total_calls if total_calls > 0 else 0.0
        avg_cost_per_minute = (total_cost / (total_duration / 60.0)) if total_duration > 0 else 0.0
        # Round cost per minute to 8 decimal places, then multiply by 60 for consistency
        avg_cost_per_minute_rounded = round(avg_cost_per_minute, 8)
        avg_cost_per_hour = avg_cost_per_minute_rounded * 60.0
        words_per_minute = (total_words / (total_duration / 60.0)) if total_duration > 0 else 0.0
        
        return {
            'total_cost': total_cost,
            'total_calls': total_calls,
            'total_words': total_words,
            'median_duration': median_duration,
            'avg_cost_per_word': avg_cost_per_word,
            'avg_cost_per_call': avg_cost_per_call,
            'avg_cost_per_minute': avg_cost_per_minute,
            'avg_cost_per_hour': avg_cost_per_hour,
            'words_per_minute': words_per_minute,
            'total_duration_seconds': total_duration
        }
    
    def _calculate_combined_statistics(self, ocr_stats, translation_stats):
        """Calculate combined OCR + Translation statistics."""
        total_cost = ocr_stats['total_cost'] + translation_stats['total_cost']
        
        # Simply add the individual rates since they represent independent processes
        combined_cost_per_minute = ocr_stats['avg_cost_per_minute'] + translation_stats['avg_cost_per_minute']
        # Round combined cost per minute to 8 decimal places, then multiply by 60 for consistency
        combined_cost_per_minute_rounded = round(combined_cost_per_minute, 8)
        combined_cost_per_hour = combined_cost_per_minute_rounded * 60.0
        
        return {
            'total_cost': total_cost,
            'combined_cost_per_minute': combined_cost_per_minute,
            'combined_cost_per_hour': combined_cost_per_hour
        }
    
    def _get_empty_statistics(self):
        """Return empty statistics structure when no data is available."""
        return {
            'ocr': {
                'total_cost': 0.0,
                'total_calls': 0,
                'median_duration': 0.0,
                'avg_cost_per_call': 0.0,
                'avg_cost_per_minute': 0.0,
                'avg_cost_per_hour': 0.0,
                'total_duration_seconds': 0.0
            },
            'translation': {
                'total_cost': 0.0,
                'total_calls': 0,
                'total_words': 0,
                'median_duration': 0.0,
                'avg_cost_per_word': 0.0,
                'avg_cost_per_minute': 0.0,
                'avg_cost_per_hour': 0.0,
                'words_per_minute': 0.0,
                'total_duration_seconds': 0.0
            },
            'openai_translation': {
                'total_cost': 0.0,
                'total_calls': 0,
                'total_words': 0,
                'median_duration': 0.0,
                'avg_cost_per_word': 0.0,
                'avg_cost_per_minute': 0.0,
                'avg_cost_per_hour': 0.0,
                'words_per_minute': 0.0,
                'total_duration_seconds': 0.0
            },
            'combined': {
                'total_cost': 0.0,
                'combined_cost_per_minute': 0.0,
                'combined_cost_per_hour': 0.0
            }
        }
    
    def _format_currency_for_export(self, amount, use_polish_format=False):
        """Format currency for export files with proper localization."""
        try:
            if use_polish_format:
                # Polish format: "0,04941340 USD"
                amount_str = f"{amount:.8f}"
                amount_str = amount_str.replace('.', ',')  # Replace decimal point with comma
                return f"{amount_str} USD"
            else:
                # English format: "$0.04941340"
                return f"${amount:.8f}"
        except Exception as e:
            log_debug(f"Error formatting currency for export: {e}")
            return f"${amount:.8f}"  # Fallback to English format
    
    def _format_number_with_separators_for_export(self, number, use_polish_format=False):
        """Format integer numbers with thousand separators for export files."""
        try:
            # Convert to integer to avoid decimal formatting issues
            num = int(number)
            
            if use_polish_format:
                # Polish format: use space as thousand separator
                num_str = str(num)
                if len(num_str) > 3:
                    formatted = ""
                    for i, digit in enumerate(reversed(num_str)):
                        if i > 0 and i % 3 == 0:
                            formatted = " " + formatted
                        formatted = digit + formatted
                    return formatted
                else:
                    return num_str
            else:
                # English format: use comma as thousand separator
                return f"{num:,}"
        except Exception as e:
            log_debug(f"Error formatting number with separators for export: {e}")
            return str(number)  # Fallback to string representation
    
    def export_statistics_csv(self, file_path, ui_lang=None, deepl_usage=None):
        """Export statistics to CSV format with proper formatting."""
        try:
            stats = self.get_statistics()
            
            # Determine if Polish formatting should be used
            use_polish_format = ui_lang and hasattr(ui_lang, 'current_lang') and ui_lang.current_lang == 'pol'
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("Category,Metric,Value\n")
                
                # OCR statistics - match GUI order with proper cost per hour calculation
                ocr = stats['ocr']
                f.write(f"OCR,Total OCR Calls,{self._format_number_with_separators_for_export(ocr['total_calls'], use_polish_format)}\n")
                # Format duration with proper Polish formatting
                duration_str = f"{ocr['median_duration']:.3f}s"
                if use_polish_format:
                    duration_str = f"{ocr['median_duration']:.3f} s".replace('.', ',')
                f.write(f"OCR,Median Duration,{duration_str}\n")
                f.write(f"OCR,Average Cost per Call,{self._format_currency_for_export(ocr['avg_cost_per_call'], use_polish_format)}\n")
                f.write(f"OCR,Average Cost per Minute,{self._format_currency_for_export(ocr['avg_cost_per_minute'], use_polish_format)}\n")
                # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                cost_per_minute_rounded = round(ocr['avg_cost_per_minute'], 8)
                cost_per_hour = cost_per_minute_rounded * 60
                f.write(f"OCR,Average Cost per Hour,{self._format_currency_for_export(cost_per_hour, use_polish_format)}\n")
                f.write(f"OCR,Total OCR Cost,{self._format_currency_for_export(ocr['total_cost'], use_polish_format)}\n")
                
                # Translation statistics - match GUI order with proper cost per hour calculation
                trans = stats['translation']
                f.write(f"Translation,Total Translation Calls,{self._format_number_with_separators_for_export(trans['total_calls'], use_polish_format)}\n")
                f.write(f"Translation,Total Words Translated,{self._format_number_with_separators_for_export(trans['total_words'], use_polish_format)}\n")
                # Format duration with proper Polish formatting
                duration_str = f"{trans['median_duration']:.3f}s"
                if use_polish_format:
                    duration_str = f"{trans['median_duration']:.3f} s".replace('.', ',')
                f.write(f"Translation,Median Duration,{duration_str}\n")
                # Format words per minute with proper decimal separator
                wpm = trans['words_per_minute']
                wpm_str = f"{wpm:.2f}"
                if use_polish_format:
                    wpm_str = wpm_str.replace('.', ',')
                f.write(f"Translation,Average Words per Minute,{wpm_str}\n")
                f.write(f"Translation,Average Cost per Word,{self._format_currency_for_export(trans['avg_cost_per_word'], use_polish_format)}\n")
                f.write(f"Translation,Average Cost per Call,{self._format_currency_for_export(trans['avg_cost_per_call'], use_polish_format)}\n")
                f.write(f"Translation,Average Cost per Minute,{self._format_currency_for_export(trans['avg_cost_per_minute'], use_polish_format)}\n")
                # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                cost_per_minute_rounded = round(trans['avg_cost_per_minute'], 8)
                cost_per_hour = cost_per_minute_rounded * 60
                f.write(f"Translation,Average Cost per Hour,{self._format_currency_for_export(cost_per_hour, use_polish_format)}\n")
                f.write(f"Translation,Total Translation Cost,{self._format_currency_for_export(trans['total_cost'], use_polish_format)}\n")
                
                # OpenAI Translation statistics - match GUI order with proper cost per hour calculation
                openai_trans = stats['openai_translation']
                f.write(f"OpenAI Translation,Total Translation Calls,{self._format_number_with_separators_for_export(openai_trans['total_calls'], use_polish_format)}\n")
                f.write(f"OpenAI Translation,Total Words Translated,{self._format_number_with_separators_for_export(openai_trans['total_words'], use_polish_format)}\n")
                # Format duration with proper Polish formatting
                duration_str = f"{openai_trans['median_duration']:.3f}s"
                if use_polish_format:
                    duration_str = f"{openai_trans['median_duration']:.3f} s".replace('.', ',')
                f.write(f"OpenAI Translation,Median Duration,{duration_str}\n")
                # Format words per minute with proper decimal separator
                wpm = openai_trans['words_per_minute']
                wpm_str = f"{wpm:.2f}"
                if use_polish_format:
                    wpm_str = wpm_str.replace('.', ',')
                f.write(f"OpenAI Translation,Average Words per Minute,{wpm_str}\n")
                f.write(f"OpenAI Translation,Average Cost per Word,{self._format_currency_for_export(openai_trans['avg_cost_per_word'], use_polish_format)}\n")
                f.write(f"OpenAI Translation,Average Cost per Call,{self._format_currency_for_export(openai_trans['avg_cost_per_call'], use_polish_format)}\n")
                f.write(f"OpenAI Translation,Average Cost per Minute,{self._format_currency_for_export(openai_trans['avg_cost_per_minute'], use_polish_format)}\n")
                # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                cost_per_minute_rounded = round(openai_trans['avg_cost_per_minute'], 8)
                cost_per_hour = cost_per_minute_rounded * 60
                f.write(f"OpenAI Translation,Average Cost per Hour,{self._format_currency_for_export(cost_per_hour, use_polish_format)}\n")
                f.write(f"OpenAI Translation,Total Translation Cost,{self._format_currency_for_export(openai_trans['total_cost'], use_polish_format)}\n")
                
                # Combined Gemini statistics - match GUI order with proper cost per hour calculation
                combined = stats['combined']
                f.write(f"Combined Gemini,Combined Cost per Minute,{self._format_currency_for_export(combined['combined_cost_per_minute'], use_polish_format)}\n")
                # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                cost_per_minute_rounded = round(combined['combined_cost_per_minute'], 8)
                cost_per_hour = cost_per_minute_rounded * 60
                f.write(f"Combined Gemini,Combined Cost per Hour,{self._format_currency_for_export(cost_per_hour, use_polish_format)}\n")
                f.write(f"Combined Gemini,Total API Cost,{self._format_currency_for_export(combined['total_cost'], use_polish_format)}\n")
                
                # DeepL section with actual value
                deepl_value = deepl_usage if deepl_usage else "N/A"
                f.write(f"DeepL,Free Monthly Limit,{deepl_value}\n")
            
            log_debug(f"Statistics exported to CSV: {file_path}")
            return True
            
        except Exception as e:
            log_debug(f"Error exporting statistics to CSV: {e}")
            return False
    
    def export_statistics_text(self, file_path, ui_lang=None, deepl_usage=None):
        """Export statistics to text summary format with proper formatting."""
        try:
            stats = self.get_statistics()
            
            # Determine if Polish formatting should be used
            use_polish_format = ui_lang and hasattr(ui_lang, 'current_lang') and ui_lang.current_lang == 'pol'
            
            with open(file_path, 'w', encoding='utf-8') as f:
                # Use Polish or English based on ui_lang parameter
                if use_polish_format:
                    f.write("Game-Changing Translator - Statystyki użycia API\n")
                    f.write("=" * 50 + "\n\n")
                    
                    # OCR Statistics - match GUI order
                    f.write("📊 Statystyki Gemini OCR\n")
                    f.write("-" * 25 + "\n")
                    ocr = stats['ocr']
                    f.write(f"Łączne wywołania OCR: {self._format_number_with_separators_for_export(ocr['total_calls'], use_polish_format)}\n")
                    f.write(f"Mediana czasu trwania: {ocr['median_duration']:.3f} s".replace('.', ',') + "\n")
                    f.write(f"Średni koszt na wywołanie: {self._format_currency_for_export(ocr['avg_cost_per_call'], use_polish_format)}\n")
                    f.write(f"Średni koszt na minutę: {self._format_currency_for_export(ocr['avg_cost_per_minute'], use_polish_format)}/min\n")
                    # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                    cost_per_minute_rounded = round(ocr['avg_cost_per_minute'], 8)
                    cost_per_hour = cost_per_minute_rounded * 60
                    f.write(f"Średni koszt na godzinę: {self._format_currency_for_export(cost_per_hour, use_polish_format)}/godz.\n")
                    f.write(f"Łączny koszt OCR: {self._format_currency_for_export(ocr['total_cost'], use_polish_format)}\n\n")
                    
                    # Translation Statistics - match GUI order
                    f.write("🔄 Statystyki tłumaczenia Gemini\n")
                    f.write("-" * 30 + "\n")
                    trans = stats['translation']
                    f.write(f"Łączne wywołania tłumaczenia: {self._format_number_with_separators_for_export(trans['total_calls'], use_polish_format)}\n")
                    f.write(f"Łącznie słów przetłumaczonych: {self._format_number_with_separators_for_export(trans['total_words'], use_polish_format)}\n")
                    f.write(f"Mediana czasu trwania: {trans['median_duration']:.3f} s".replace('.', ',') + "\n")
                    # Format words per minute with proper decimal separator
                    wpm_str = f"{trans['words_per_minute']:.2f}".replace('.', ',')
                    f.write(f"Średnia słów na minutę: {wpm_str}\n")
                    f.write(f"Średni koszt na słowo: {self._format_currency_for_export(trans['avg_cost_per_word'], use_polish_format)}\n")
                    f.write(f"Średni koszt na wywołanie: {self._format_currency_for_export(trans['avg_cost_per_call'], use_polish_format)}\n")
                    f.write(f"Średni koszt na minutę: {self._format_currency_for_export(trans['avg_cost_per_minute'], use_polish_format)}/min\n")
                    # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                    cost_per_minute_rounded = round(trans['avg_cost_per_minute'], 8)
                    cost_per_hour = cost_per_minute_rounded * 60
                    f.write(f"Średni koszt na godzinę: {self._format_currency_for_export(cost_per_hour, use_polish_format)}/godz.\n")
                    f.write(f"Łączny koszt tłumaczenia: {self._format_currency_for_export(trans['total_cost'], use_polish_format)}\n\n")
                    
                    # Combined Statistics - match GUI order
                    f.write("💰 Łączne statystyki API\n")
                    f.write("-" * 25 + "\n")
                    combined = stats['combined']
                    f.write(f"Łączny koszt na minutę: {self._format_currency_for_export(combined['combined_cost_per_minute'], use_polish_format)}/min\n")
                    # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                    cost_per_minute_rounded = round(combined['combined_cost_per_minute'], 8)
                    cost_per_hour = cost_per_minute_rounded * 60
                    f.write(f"Łączny koszt na godzinę: {self._format_currency_for_export(cost_per_hour, use_polish_format)}/godz.\n")
                    f.write(f"Łączny koszt API: {self._format_currency_for_export(combined['total_cost'], use_polish_format)}\n\n")
                    
                    # DeepL section with actual value
                    f.write("📈 Monitor użycia DeepL\n")
                    f.write("-" * 25 + "\n")
                    deepl_value = deepl_usage if deepl_usage else "N/A"
                    f.write(f"Darmowy miesięczny limit: {deepl_value}\n\n")
                    
                else:
                    f.write("Game-Changing Translator - API Usage Statistics\n")
                    f.write("=" * 50 + "\n\n")
                    
                    # OCR Statistics - match GUI order
                    f.write("📊 Gemini OCR Statistics\n")
                    f.write("-" * 25 + "\n")
                    ocr = stats['ocr']
                    f.write(f"Total OCR Calls: {self._format_number_with_separators_for_export(ocr['total_calls'], use_polish_format)}\n")
                    f.write(f"Median Duration: {ocr['median_duration']:.3f}s\n")
                    f.write(f"Average Cost per Call: {self._format_currency_for_export(ocr['avg_cost_per_call'], use_polish_format)}\n")
                    f.write(f"Average Cost per Minute: {self._format_currency_for_export(ocr['avg_cost_per_minute'], use_polish_format)}/min\n")
                    # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                    cost_per_minute_rounded = round(ocr['avg_cost_per_minute'], 8)
                    cost_per_hour = cost_per_minute_rounded * 60
                    f.write(f"Average Cost per Hour: {self._format_currency_for_export(cost_per_hour, use_polish_format)}/hr\n")
                    f.write(f"Total OCR Cost: {self._format_currency_for_export(ocr['total_cost'], use_polish_format)}\n\n")
                    
                    # Translation Statistics - match GUI order
                    f.write("🔄 Gemini Translation Statistics\n")
                    f.write("-" * 30 + "\n")
                    trans = stats['translation']
                    f.write(f"Total Translation Calls: {self._format_number_with_separators_for_export(trans['total_calls'], use_polish_format)}\n")
                    f.write(f"Total Words Translated: {self._format_number_with_separators_for_export(trans['total_words'], use_polish_format)}\n")
                    f.write(f"Median Duration: {trans['median_duration']:.3f}s\n")
                    f.write(f"Average Words per Minute: {trans['words_per_minute']:.2f}\n")
                    f.write(f"Average Cost per Word: {self._format_currency_for_export(trans['avg_cost_per_word'], use_polish_format)}\n")
                    f.write(f"Average Cost per Call: {self._format_currency_for_export(trans['avg_cost_per_call'], use_polish_format)}\n")
                    f.write(f"Average Cost per Minute: {self._format_currency_for_export(trans['avg_cost_per_minute'], use_polish_format)}/min\n")
                    # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                    cost_per_minute_rounded = round(trans['avg_cost_per_minute'], 8)
                    cost_per_hour = cost_per_minute_rounded * 60
                    f.write(f"Average Cost per Hour: {self._format_currency_for_export(cost_per_hour, use_polish_format)}/hr\n")
                    f.write(f"Total Translation Cost: {self._format_currency_for_export(trans['total_cost'], use_polish_format)}\n\n")
                    
                    # Combined Statistics - match GUI order
                    f.write("💰 Combined API Statistics\n")
                    f.write("-" * 25 + "\n")
                    combined = stats['combined']
                    f.write(f"Combined Cost per Minute: {self._format_currency_for_export(combined['combined_cost_per_minute'], use_polish_format)}/min\n")
                    # Fix cost per hour calculation: round to 8 decimal places, then multiply by 60
                    cost_per_minute_rounded = round(combined['combined_cost_per_minute'], 8)
                    cost_per_hour = cost_per_minute_rounded * 60
                    f.write(f"Combined Cost per Hour: {self._format_currency_for_export(cost_per_hour, use_polish_format)}/hr\n")
                    f.write(f"Total API Cost: {self._format_currency_for_export(combined['total_cost'], use_polish_format)}\n\n")
                    
                    # DeepL section with actual value
                    f.write("📈 DeepL Usage Monitor\n")
                    f.write("-" * 25 + "\n")
                    deepl_value = deepl_usage if deepl_usage else "N/A"
                    f.write(f"Free Monthly Limit: {deepl_value}\n\n")
                
                f.write(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            log_debug(f"Statistics exported to text: {file_path}")
            return True
            
        except Exception as e:
            log_debug(f"Error exporting statistics to text: {e}")
            return False
