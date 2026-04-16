{# Jinja2 CV template, santifer/career-ops style. Rendered by cv_renderer.py. #}
# {{ profile.name }}

{{ profile.email }} &middot; {{ profile.location }}
{% if profile.github %}[GitHub]({{ profile.github }}){% endif %}{% if profile.linkedin %} &middot; [LinkedIn]({{ profile.linkedin }}){% endif %}

---

## Summary

{% if job %}**Targeting {{ job.title }} at {{ job.company }}** — {% endif %}{{ profile.summary }}

## Skills

{% for bucket, items in profile.skills.items() -%}
**{{ bucket|capitalize }}**: {{ items | join(', ') }}
{% endfor %}
{% if tailor_added %}
_Emphasised for this role: {{ tailor_added | join(', ') }}._
{% endif %}

## Experience

{% for role in profile.experience %}
### {{ role.title }} — {{ role.company }}
*{{ role.dates }}*

{% for bullet in role.bullets %}- {{ bullet }}
{% endfor %}
{% endfor %}

## Education

{% for edu in profile.education %}
**{{ edu.degree }}**, {{ edu.school }} *({{ edu.dates }})*
{% endfor %}
