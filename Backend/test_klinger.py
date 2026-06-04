from bot.klinger import get_live_klinger_data  # adjust path if needed

if __name__ == "__main__":
    data = get_live_klinger_data()
    print("Klinger Oscillator Live Data:")
    print(data)
