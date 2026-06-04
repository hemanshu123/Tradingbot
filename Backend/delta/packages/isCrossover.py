def isCrossOver(L_fisher, L_trigger, C_fisher, C_trigger):
    """
    Detects crossover between Fisher and Trigger values.
    
    Args:
        L_fisher (float): Previous Fisher value
        L_trigger (float): Previous Trigger value
        C_fisher (float): Current Fisher value
        C_trigger (float): Current Trigger value
    
    Returns:
        str: "bullish" if bullish crossover,
             "bearish" if bearish crossover,
             None if no crossover
    """
    # Bullish crossover: Fisher goes from below Trigger to above Trigger
    if L_fisher < L_trigger and C_fisher > C_trigger:
        return "buy"
    
    # Bearish crossover: Fisher goes from above Trigger to below Trigger
    if L_fisher > L_trigger and C_fisher < C_trigger:
        return "sell"
    
    # No crossover
    return "no crossover"
    
    

