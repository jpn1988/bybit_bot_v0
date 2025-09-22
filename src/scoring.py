#!/usr/bin/env python3
"""
Module de scoring pour classer les paires qui ont passé les filtres.

Ce module fournit une classe ScoringEngine qui calcule un score composite
basé sur le funding, le spread et la volatilité, puis sélectionne les
meilleures paires selon ce score.
"""

import math
from typing import List, Tuple, Dict, Optional
from logging_setup import setup_logging


class ScoringEngine:
    """
    Moteur de scoring pour classer les paires de trading.
    
    Calcule un score composite basé sur :
    - Le funding rate (pondéré, positif = meilleur)
    - Le volume (pondéré avec log, plus élevé = meilleur)
    - Le spread (pondéré, négatif = pénalité)
    - La volatilité (pondérée, négatif = pénalité)
    
    Formule : (weight_funding × funding) + (weight_volume × log(volume)) - (weight_spread × spread) - (weight_volatility × volatility)
    """
    
    def __init__(self, config: Dict, logger=None):
        """
        Initialise le moteur de scoring.
        
        Args:
            config: Configuration contenant les paramètres de scoring
            logger: Logger pour les messages (optionnel)
        """
        self.logger = logger or setup_logging()
        
        # Extraire les paramètres de scoring
        scoring_config = config.get('scoring', {})
        self.weight_funding = scoring_config.get('weight_funding', 1000)
        self.weight_volume = scoring_config.get('weight_volume', 10)
        self.weight_spread = scoring_config.get('weight_spread', 200)
        self.weight_volatility = scoring_config.get('weight_volatility', 50)
        self.top_n = scoring_config.get('top_n', 1)
        
        self.logger.debug(f"🎯 ScoringEngine initialisé | weight_funding={self.weight_funding} | "
                         f"weight_volume={self.weight_volume} | weight_spread={self.weight_spread} | "
                         f"weight_volatility={self.weight_volatility} | top_n={self.top_n}")
    
    def compute_score(self, funding: float, volume: float, spread: float, volatility: float) -> float:
        """
        Calcule le score composite d'une paire.
        
        Args:
            funding: Taux de funding (positif = meilleur)
            volume: Volume en USDT (plus élevé = meilleur)
            spread: Spread en pourcentage (plus bas = meilleur)
            volatility: Volatilité en pourcentage (plus bas = meilleur)
            
        Returns:
            Score composite (plus élevé = meilleur)
        """
        # Calculer log(volume) avec protection contre volume = 0
        log_volume = math.log(max(volume, 1.0))
        
        # Formule : (weight_funding × funding) + (weight_volume × log(volume)) - (weight_spread × spread) - (weight_volatility × volatility)
        funding_component = self.weight_funding * funding
        volume_component = self.weight_volume * log_volume
        spread_penalty = self.weight_spread * spread
        volatility_penalty = self.weight_volatility * volatility
        
        score = funding_component + volume_component - spread_penalty - volatility_penalty
        
        # Log détaillé avec toutes les composantes
        self.logger.debug(f"📊 Score détaillé | funding={funding:.6f} (×{self.weight_funding}) = {funding_component:.2f} | "
                         f"volume={volume:.0f} → log={log_volume:.3f} (×{self.weight_volume}) = {volume_component:.2f} | "
                         f"spread={spread:.6f} (×{self.weight_spread}) = -{spread_penalty:.2f} | "
                         f"volatility={volatility:.6f} (×{self.weight_volatility}) = -{volatility_penalty:.2f} | "
                         f"SCORE FINAL = {score:.2f}")
        
        return score
    
    def rank_candidates(self, candidates: List[Tuple]) -> List[Tuple]:
        """
        Classe les candidats par score et retourne les top_n meilleures paires.
        
        Args:
            candidates: Liste des paires filtrées sous forme de tuples
                       Format attendu : (symbol, funding, volume, funding_time_remaining, spread_pct, volatility_pct)
                       ou variantes avec moins d'éléments
        
        Returns:
            Liste des top_n meilleures paires avec leur score ajouté
        """
        if not candidates:
            self.logger.warning("⚠️ Aucun candidat à classer")
            return []
        
        # ============================================
        # BLOC 1: Afficher toutes les paires valides (celles qui ont passé les filtres)
        # ============================================
        self.logger.info("=" * 80)
        self.logger.info(f"📋 ÉTAPE 1: Paires valides après filtrage ({len(candidates)} paires)")
        self.logger.info("=" * 80)
        
        # Formater et afficher le tableau des paires filtrées
        table_lines = self._format_candidate_table(candidates, show_score=False)
        for line in table_lines:
            self.logger.info(line)
        
        self.logger.info("-" * 80)
        
        # Calculer les scores pour toutes les paires
        scored_candidates = []
        for candidate in candidates:
            symbol = candidate[0]
            funding = candidate[1]
            spread = candidate[4] if len(candidate) > 4 else 0.0
            volatility = candidate[5] if len(candidate) > 5 else 0.0
            
            # Récupérer le volume (index 2)
            volume = candidate[2] if len(candidate) > 2 else 0.0
            
            # Calculer le score
            score = self.compute_score(funding, volume, spread, volatility)
            
            # Ajouter le score à la fin du tuple
            scored_candidate = candidate + (score,)
            scored_candidates.append(scored_candidate)
        
        # Trier par score décroissant (meilleur score en premier)
        scored_candidates.sort(key=lambda x: x[-1], reverse=True)
        
        # Sélectionner les top_n meilleures
        top_candidates = scored_candidates[:self.top_n]
        
        # ============================================
        # BLOC 2: Afficher les paires retenues après classement par score
        # ============================================
        self.logger.info("=" * 80)
        self.logger.info(f"🏆 ÉTAPE 2: Paires retenues après classement par score ({len(top_candidates)}/{len(candidates)} paires)")
        self.logger.info("=" * 80)
        
        # Formater et afficher le tableau des paires retenues avec score
        table_lines = self._format_candidate_table(top_candidates, show_score=True)
        for line in table_lines:
            self.logger.info(line)
        
        self.logger.info("=" * 80)
        self.logger.info(f"✅ Classement terminé: {len(top_candidates)} paires sélectionnées pour le trading")
        self.logger.info("=" * 80)
        
        return top_candidates
    
    def _format_candidate_table(self, candidates, show_score=False):
        """
        Formate une liste de candidats en tableau avec colonnes alignées.
        
        Args:
            candidates: Liste des candidats à formater
            show_score: Si True, affiche la colonne score
            
        Returns:
            Liste des lignes formatées du tableau
        """
        if not candidates:
            return []
        
        # Calculer les largeurs de colonnes
        symbol_w = max(12, max(len(c[0]) for c in candidates))
        funding_w = 10
        volume_w = 10
        spread_w = 9
        volatility_w = 11
        funding_time_w = 12
        score_w = 10 if show_score else 0
        
        # Créer l'en-tête
        if show_score:
            header = (
                f"{'Symbole':<{symbol_w}} | {'Funding %':>{funding_w}} | "
                f"{'Volume (M)':>{volume_w}} | {'Spread %':>{spread_w}} | "
                f"{'Volatilité %':>{volatility_w}} | {'Funding T':>{funding_time_w}} | "
                f"{'Score':>{score_w}}"
            )
            sep = (
                f"{'-'*symbol_w}-+-{'-'*funding_w}-+-{'-'*volume_w}-+-"
                f"{'-'*spread_w}-+-{'-'*volatility_w}-+-{'-'*funding_time_w}-+-"
                f"{'-'*score_w}"
            )
        else:
            header = (
                f"{'Symbole':<{symbol_w}} | {'Funding %':>{funding_w}} | "
                f"{'Volume (M)':>{volume_w}} | {'Spread %':>{spread_w}} | "
                f"{'Volatilité %':>{volatility_w}} | {'Funding T':>{funding_time_w}}"
            )
            sep = (
                f"{'-'*symbol_w}-+-{'-'*funding_w}-+-{'-'*volume_w}-+-"
                f"{'-'*spread_w}-+-{'-'*volatility_w}-+-{'-'*funding_time_w}"
            )
        
        lines = [header, sep]
        
        # Ajouter les lignes de données
        for candidate in candidates:
            symbol = candidate[0]
            funding = candidate[1]
            volume = candidate[2]
            funding_time = candidate[3] if len(candidate) > 3 else "-"
            spread = candidate[4] if len(candidate) > 4 else 0.0
            volatility = candidate[5] if len(candidate) > 5 else 0.0
            
            funding_pct = funding * 100.0
            volume_millions = volume / 1_000_000 if volume else 0
            spread_pct = spread * 100.0
            volatility_pct = volatility * 100.0
            
            if show_score:
                score = candidate[-1]  # Le score est le dernier élément
                line = (
                    f"{symbol:<{symbol_w}} | {funding_pct:+{funding_w-1}.4f}% | "
                    f"{volume_millions:>{volume_w-1}.1f}M | {spread_pct:>{spread_w-1}.3f}% | "
                    f"{volatility_pct:>{volatility_w-1}.3f}% | {funding_time:>{funding_time_w}} | "
                    f"{score:+{score_w-1}.4f}"
                )
            else:
                line = (
                    f"{symbol:<{symbol_w}} | {funding_pct:+{funding_w-1}.4f}% | "
                    f"{volume_millions:>{volume_w-1}.1f}M | {spread_pct:>{spread_w-1}.3f}% | "
                    f"{volatility_pct:>{volatility_w-1}.3f}% | {funding_time:>{funding_time_w}}"
                )
            
            lines.append(line)
        
        return lines
    
    def get_scoring_config(self) -> Dict:
        """
        Retourne la configuration de scoring actuelle.
        
        Returns:
            Dictionnaire avec les paramètres de scoring
        """
        return {
            'weight_funding': self.weight_funding,
            'weight_volume': self.weight_volume,
            'weight_spread': self.weight_spread,
            'weight_volatility': self.weight_volatility,
            'top_n': self.top_n
        }
