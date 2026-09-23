# planted bypass: api key in URL
# The value is the literal placeholder EXAMPLEKEY000000, never a key. It keeps
# the shape the lint must match -- eight or more alphanumerics after apiKey= --
# while carrying no entropy for the gitleaks hook to trip on.
curl -sS "https://api.the-odds-api.com/v4/sports/upcoming/odds/?apiKey=EXAMPLEKEY000000"
