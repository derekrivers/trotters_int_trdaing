# Lessons

## During Implementation

- a Python-native build step was enough for this workflow; bringing in a frontend framework or JS bundler would have been unnecessary scope
- keeping the existing HTML structure and class vocabulary stable let the reskin land without reopening auth, CSRF, or operator-route behavior

## Durable Takeaways

- the dashboard can adopt a coherent admin visual system without moving truth out of the server-rendered app
- future dashboard polish should extend the compiled CSS asset and layout helpers instead of adding new inline style blocks back into `dashboard.py`
