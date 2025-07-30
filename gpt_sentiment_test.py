#!/usr/bin/env python3
"""
Test complet du nouveau service d'analyse de sentiment GPT
Tests critiques selon la demande de révision
"""

import sys
import time
sys.path.append('/app/backend')

class GPTSentimentTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")
        return success

    def test_gpt_sentiment_service_direct(self):
        """Test du service GPT sentiment directement"""
        try:
            from gpt_sentiment_service import gpt_sentiment_analyzer, analyze_text_sentiment
            
            # Test texts from the review request
            test_texts = [
                "Guy Losbar annonce d'excellents projets pour le développement durable de la Guadeloupe",
                "Grave accident de la route à Basse-Terre, plusieurs victimes",
                "Le Conseil Départemental vote le budget 2025",
                "Festival de musique créole : une ambiance exceptionnelle à Pointe-à-Pitre"
            ]
            
            results = []
            for text in test_texts:
                result = analyze_text_sentiment(text)
                results.append({
                    'text': text[:50] + "...",
                    'sentiment': result['polarity'],
                    'score': result['score'],
                    'emotions': result['analysis_details']['emotions'][:3],  # First 3 emotions
                    'themes': result['analysis_details']['themes'][:3],  # First 3 themes
                    'method': result['analysis_details']['method']
                })
            
            # Check if GPT method is used
            gpt_methods = [r for r in results if 'gpt' in r['method']]
            success = len(gpt_methods) > 0
            
            if success:
                details = f"- GPT sentiment working: {len(gpt_methods)}/{len(results)} used GPT"
                for r in results:
                    print(f"  • {r['text']} → {r['sentiment']} ({r['score']:.2f}) | {r['method']}")
            else:
                details = f"- GPT sentiment not working: methods used: {[r['method'] for r in results]}"
            
            return self.log_test("GPT Sentiment Service Direct", success, details)
        except Exception as e:
            return self.log_test("GPT Sentiment Service Direct", False, f"- Error: {str(e)}")

    def test_gpt_sentiment_contextual_analysis(self):
        """Test de l'analyse contextuelle Guadeloupe"""
        try:
            from gpt_sentiment_service import analyze_text_sentiment
            
            # Test Guadeloupe-specific contexts
            guadeloupe_texts = [
                "Guy Losbar présente les nouveaux projets du Conseil Départemental pour l'éducation",
                "Accident grave sur la route de Basse-Terre, intervention des secours",
                "Nouvelle école inaugurée à Pointe-à-Pitre par le CD971",
                "Festival créole : succès populaire dans toute la Guadeloupe"
            ]
            
            contextual_results = []
            for text in guadeloupe_texts:
                result = analyze_text_sentiment(text)
                
                # Check for Guadeloupe context
                guadeloupe_context = result['analysis_details'].get('guadeloupe_context', '')
                has_context = bool(guadeloupe_context and len(guadeloupe_context) > 10)
                
                contextual_results.append({
                    'text': text[:40] + "...",
                    'sentiment': result['polarity'],
                    'has_guadeloupe_context': has_context,
                    'themes': result['analysis_details']['themes'],
                    'emotions': result['analysis_details']['emotions'],
                    'context': guadeloupe_context[:100] + "..." if guadeloupe_context else ""
                })
                
                print(f"  • {text[:60]}...")
                print(f"    Sentiment: {result['polarity']} ({result['score']:.2f})")
                print(f"    Émotions: {result['analysis_details']['emotions'][:3]}")
                print(f"    Thèmes: {result['analysis_details']['themes'][:3]}")
                print(f"    Contexte Guadeloupe: {guadeloupe_context[:100]}..." if guadeloupe_context else "    Contexte: Non détecté")
                print()
            
            # Check quality of contextual analysis
            with_context = [r for r in contextual_results if r['has_guadeloupe_context']]
            with_themes = [r for r in contextual_results if len(r['themes']) > 0]
            with_emotions = [r for r in contextual_results if len(r['emotions']) > 0]
            
            success = len(with_themes) >= 2 and len(with_emotions) >= 2
            
            if success:
                details = f"- Contextual analysis working: {len(with_context)} with context, {len(with_themes)} with themes, {len(with_emotions)} with emotions"
            else:
                details = f"- Contextual analysis weak: context={len(with_context)}, themes={len(with_themes)}, emotions={len(with_emotions)}"
            
            return self.log_test("GPT Sentiment Contextual Analysis", success, details)
        except Exception as e:
            return self.log_test("GPT Sentiment Contextual Analysis", False, f"- Error: {str(e)}")

    def test_gpt_sentiment_quality_analysis(self):
        """Test de la qualité des analyses (émotions, thèmes, contexte)"""
        try:
            from gpt_sentiment_service import analyze_text_sentiment
            
            # Test with rich content for quality analysis
            rich_text = "Le Conseil Départemental de la Guadeloupe, sous la direction de Guy Losbar, a voté un budget ambitieux pour 2025. Ce budget prévoit des investissements majeurs dans l'éducation, avec la construction de nouvelles écoles, et dans les infrastructures routières pour améliorer la sécurité. Les familles guadeloupéennes bénéficieront également d'aides sociales renforcées."
            
            print(f"Analyse du texte riche: {rich_text[:100]}...")
            result = analyze_text_sentiment(rich_text)
            
            # Check quality indicators
            emotions = result['analysis_details']['emotions']
            themes = result['analysis_details']['themes']
            keywords = result['analysis_details']['keywords']
            explanation = result['analysis_details']['explanation']
            guadeloupe_context = result['analysis_details']['guadeloupe_context']
            confidence = result['analysis_details']['confidence']
            
            print(f"  Sentiment: {result['polarity']} (score: {result['score']:.3f})")
            print(f"  Émotions détectées: {emotions}")
            print(f"  Thèmes identifiés: {themes}")
            print(f"  Mots-clés: {keywords}")
            print(f"  Explication: {explanation[:150]}...")
            print(f"  Contexte Guadeloupe: {guadeloupe_context[:150]}...")
            print(f"  Confiance: {confidence}")
            print(f"  Méthode: {result['analysis_details']['method']}")
            
            # Quality checks
            has_emotions = len(emotions) >= 2
            has_themes = len(themes) >= 2
            has_keywords = len(keywords) >= 3
            has_explanation = len(explanation) > 20
            has_context = len(guadeloupe_context) > 10
            good_confidence = confidence > 0.6
            
            quality_score = sum([has_emotions, has_themes, has_keywords, has_explanation, has_context, good_confidence])
            success = quality_score >= 4  # At least 4/6 quality indicators
            
            if success:
                details = f"- Quality analysis: {quality_score}/6 indicators, emotions={len(emotions)}, themes={len(themes)}, confidence={confidence}"
            else:
                details = f"- Quality insufficient: {quality_score}/6 indicators, missing: emotions={has_emotions}, themes={has_themes}, explanation={has_explanation}"
            
            return self.log_test("GPT Sentiment Quality Analysis", success, details)
        except Exception as e:
            return self.log_test("GPT Sentiment Quality Analysis", False, f"- Error: {str(e)}")

    def test_gpt_sentiment_performance_costs(self):
        """Test de performance et coûts"""
        try:
            from gpt_sentiment_service import analyze_text_sentiment
            
            # Test performance with multiple texts
            test_texts = [
                "Excellent projet du CD971 pour l'environnement",
                "Problème de circulation à Pointe-à-Pitre",
                "Nouvelle initiative de Guy Losbar pour l'éducation"
            ]
            
            print("Test de performance avec 3 textes...")
            start_time = time.time()
            results = []
            
            for i, text in enumerate(test_texts):
                text_start = time.time()
                result = analyze_text_sentiment(text)
                text_time = time.time() - text_start
                
                results.append({
                    'method': result['analysis_details']['method'],
                    'processing_time': text_time
                })
                
                print(f"  Texte {i+1}: {text[:50]}... → {result['polarity']} ({text_time:.1f}s)")
            
            total_time = time.time() - start_time
            avg_time = total_time / len(test_texts)
            
            # Check if gpt-4o-mini is used (cost optimization)
            gpt_mini_used = any('gpt-4o-mini' in r['method'] for r in results)
            reasonable_time = avg_time < 15  # Should be under 15 seconds per text on average
            
            success = gpt_mini_used and reasonable_time
            
            print(f"  Temps total: {total_time:.1f}s, Temps moyen: {avg_time:.1f}s")
            print(f"  Modèle gpt-4o-mini utilisé: {gpt_mini_used}")
            
            if success:
                details = f"- Performance good: avg_time={avg_time:.1f}s, gpt-4o-mini used: {gpt_mini_used}"
            else:
                details = f"- Performance issues: avg_time={avg_time:.1f}s, gpt-4o-mini: {gpt_mini_used}"
            
            return self.log_test("GPT Sentiment Performance & Costs", success, details)
        except Exception as e:
            return self.log_test("GPT Sentiment Performance & Costs", False, f"- Error: {str(e)}")

    def test_gpt_sentiment_utility_functions(self):
        """Test des fonctions utilitaires"""
        try:
            from gpt_sentiment_service import analyze_text_sentiment, analyze_articles_sentiment
            
            print("Test des fonctions utilitaires...")
            
            # Test analyze_text_sentiment function
            text_result = analyze_text_sentiment("Guy Losbar annonce de bonnes nouvelles pour la Guadeloupe")
            text_success = text_result['polarity'] in ['positive', 'negative', 'neutral']
            
            print(f"  analyze_text_sentiment: {text_result['polarity']} (score: {text_result['score']:.3f})")
            
            # Test analyze_articles_sentiment function
            mock_articles = [
                {'title': 'Excellent festival à Pointe-à-Pitre', 'content': 'Ambiance formidable'},
                {'title': 'Accident grave à Basse-Terre', 'content': 'Plusieurs victimes'},
                {'title': 'Budget voté par le CD971', 'content': 'Nouvelles mesures sociales'}
            ]
            
            articles_result = analyze_articles_sentiment(mock_articles)
            articles_success = (
                'articles' in articles_result and 
                'summary' in articles_result and
                len(articles_result['articles']) == 3
            )
            
            if articles_success:
                summary = articles_result['summary']
                print(f"  analyze_articles_sentiment: {len(articles_result['articles'])} articles analysés")
                print(f"    Distribution: {summary.get('sentiment_distribution', {})}")
                print(f"    Score moyen: {summary.get('average_sentiment_score', 0):.3f}")
                print(f"    Méthode: {summary.get('analysis_method', 'unknown')}")
            
            success = text_success and articles_success
            
            if success:
                details = f"- Utility functions working: text_sentiment={text_result['polarity']}, articles_analyzed={len(articles_result['articles'])}"
            else:
                details = f"- Utility functions failed: text_success={text_success}, articles_success={articles_success}"
            
            return self.log_test("GPT Sentiment Utility Functions", success, details)
        except Exception as e:
            return self.log_test("GPT Sentiment Utility Functions", False, f"- Error: {str(e)}")

    def run_all_tests(self):
        """Run all GPT sentiment tests"""
        print("🤖 TEST COMPLET DU NOUVEAU SERVICE D'ANALYSE DE SENTIMENT GPT")
        print("=" * 80)
        print()
        
        print("1️⃣ TEST DU SERVICE GPT SENTIMENT DIRECTEMENT")
        self.test_gpt_sentiment_service_direct()
        print()
        
        print("2️⃣ TEST DES FONCTIONS UTILITAIRES")
        self.test_gpt_sentiment_utility_functions()
        print()
        
        print("3️⃣ TEST DE L'ANALYSE CONTEXTUELLE")
        self.test_gpt_sentiment_contextual_analysis()
        print()
        
        print("4️⃣ TEST DE LA QUALITÉ DES ANALYSES")
        self.test_gpt_sentiment_quality_analysis()
        print()
        
        print("5️⃣ TEST DE PERFORMANCE ET COÛTS")
        self.test_gpt_sentiment_performance_costs()
        print()
        
        print("=" * 80)
        print(f"🎯 RÉSULTATS FINAUX: {self.tests_passed}/{self.tests_run} tests réussis")
        
        if self.tests_passed == self.tests_run:
            print("✅ NOUVEAU SERVICE GPT SENTIMENT: ENTIÈREMENT OPÉRATIONNEL")
            print("🎉 Analyses de sentiment beaucoup plus riches et précises que l'ancien service local")
        else:
            print(f"⚠️ PROBLÈMES DÉTECTÉS: {self.tests_run - self.tests_passed} tests échoués")
        
        return self.tests_passed == self.tests_run

if __name__ == "__main__":
    tester = GPTSentimentTester()
    tester.run_all_tests()