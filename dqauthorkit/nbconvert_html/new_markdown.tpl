{% extends 'markdown.tpl' %}

{% block input %}
{% raw %}
    {% highlight python %}
{% endraw %}
{{ cell.source}}
{% raw %}
    {% endhighlight %}
{% endraw %}

{% endblock input %}