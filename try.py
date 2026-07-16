import plotly.graph_objects as go

fig = go.Figure(data=[go.Sankey(
    node=dict(
        pad=15,          # Отступ между узлами
        thickness=20,    # Толщина узлов
        line=dict(color="black", width=0.5),  # Граница узлов
        label=["A1", "A2", "B1", "B2", "C1", "C2"],  # Названия узлов
        color="blue"     # Цвет узлов
    ),
    link=dict(
        source=[0, 1, 0, 2, 3, 3],  # Индексы источников
        target=[2, 3, 3, 4, 4, 0],  # Индексы целей
        value=[8, 4, 3, 8, 4, 2]  # Величины потоков
    ),
    )
                      
                ]
)

fig.update_layout(title_text="Basic Sankey Diagram", font_size=10)
fig.show()
