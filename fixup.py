import io

p = "main.py"
s = io.open(p, encoding="utf-8").read()

pares = [
    ('values=["Local", "Ally"]', 'values=["Local", "Remoto"]'),
    (
        'self.destino_var = ctk.StringVar(value=cfg.get("destino", "Local"))',
        'destino_cfg = cfg.get("destino", "Local")\n'
        '        if destino_cfg == "Ally":\n'
        '            destino_cfg = "Remoto"\n'
        '        self.destino_var = ctk.StringVar(value=destino_cfg)',
    ),
    ("Local ou ROG Ally à distância", "Local ou destino remoto (Ally / sessão fantasma)"),
    ("IP da Ally (ex: 100.50.10.2)", "IP do destino (127.0.0.1 = sessão fantasma)"),
    ("Indica o IP da Ally no campo", "Indica o IP do destino no campo"),
    ("Erro Ally", "Erro remoto"),
    ("A Ally desligou-se", "O destino remoto desligou-se"),
    ("Ally recusou o vídeo", "O destino recusou o vídeo"),
    ("IP da Ally em falta", "IP do destino em falta"),
    ("Token recusado pela Ally", "Token recusado pelo destino"),
    ("A fechar o CS2 na Ally...", "A fechar o CS2 no destino remoto..."),
    (
        "CS2 fechado na Ally ({n}). Conta livre para jogar no PC.",
        "CS2/Steam fechados no destino ({n}). Conta livre para o PC.",
    ),
    ("O CS2 já não estava aberto na Ally.", "O CS2 já não estava aberto no destino."),
    ("Erro ao fechar CS2 na Ally", "Erro ao fechar CS2 no destino"),
    ("A abrir o CS2 na Ally...", "A abrir o CS2 no destino remoto..."),
    (
        "Ordem enviada à Ally. Quando o CS2 abrir lá, o farm retoma sozinho.",
        "Ordem enviada. Quando o CS2 abrir no destino, o farm retoma sozinho.",
    ),
    ("Erro ao abrir CS2 na Ally", "Erro ao abrir CS2 no destino"),
    ("Ligado à Ally. Sessão iniciada.", "Ligado ao destino remoto. Sessão iniciada."),
    ('na ROG Ally" if remoto else "LOCAL"', 'REMOTO" if remoto else "LOCAL"'),
    ("ALLY — ECRÃ AO VIVO", "REMOTO — ECRÃ AO VIVO"),
    ("Ally remota", "Destino remoto"),
    ("A ligar à Ally...", "A ligar ao destino remoto..."),
    ("cs2.exe DETETADO na Ally", "cs2.exe DETETADO no destino remoto"),
    ("cs2.exe na ROG Ally", "cs2.exe no destino remoto"),
    ("CS2 aberto na Ally, a retomar o farm sozinho.", "CS2 aberto no destino, a retomar o farm sozinho."),
    ("NÃO ENCONTRADO na Ally", "NÃO ENCONTRADO no destino remoto"),
    ("À espera do cs2.exe na Ally...", "À espera do cs2.exe no destino remoto..."),
    ("VOLTAR AO FARM NA ALLY (abre o CS2 lá)", "VOLTAR AO FARM REMOTO (abre o CS2 lá)"),
    ("A fechar o CS2 na Ally", "A fechar o CS2 no destino remoto"),
    ("a ligar à Ally", "a ligar ao destino remoto"),
]

for a, b in pares:
    s = s.replace(a, b)

s = s.replace('== "Ally"', '== "Remoto"')
s = s.replace("'Ally'", "'Remoto'")

io.open(p, "w", encoding="utf-8").write(s)
print("substituicoes feitas")
