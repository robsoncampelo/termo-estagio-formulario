import gradio as gr
from datetime import datetime
from num2words import num2words
import re
# gradio==5.34.2
# num2words==0.5.14

from email_validator import validate_email, EmailNotValidError
import dns.resolver
import gradio as gr


# Resolver com DNS públicos e timeouts curtos
def _make_resolver():
    r = dns.resolver.Resolver(configure=True)
    # Use DNS públicos; ajuste se sua rede bloquear
    r.nameservers = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]
    r.lifetime = 3.0   # tempo total por consulta
    r.timeout  = 2.0   # timeout por servidor
    return r

def _has_mx_or_a(domain: str, resolver=None) -> bool:
    if resolver is None:
        resolver = _make_resolver()
    try:
        resolver.resolve(domain, "MX")
        return True
    except Exception:
        try:
            resolver.resolve(domain, "A")
            return True
        except Exception:
            return False

def _has_mx_or_a_or_parent(domain: str, resolver=None):
    if resolver is None:
        resolver = _make_resolver()

    def check(d):
        try:
            return _has_mx_or_a(d, resolver=resolver)
        except (dns.resolver.LifetimeTimeout, dns.exception.Timeout):
            # Rede/DNS indisponível → não condene o e-mail; devolva None (desconhecido)
            return None
        except Exception:
            return False

    # Tenta no próprio domínio
    res = check(domain)
    if res is True:
        return True
    if res is None:
        return None  # indeterminado por timeout

    # Tenta no domínio-pai
    parts = domain.split(".")
    if len(parts) > 2:
        parent = ".".join(parts[1:])
        res_p = check(parent)
        if res_p is True:
            return True
        if res_p is None:
            return None

    return False

def validar_email_estrito(valor: str):
    if not (valor and valor.strip()):
        return gr.update(value="", elem_classes=[])

    try:
        info = validate_email(
            valor,
            allow_smtputf8=False,      # sem acentos no local-part
            check_deliverability=False # DNS faremos abaixo
        )
        addr = info.normalized
        local, domain = addr.rsplit("@", 1)

        # Bloqueia Unicode também no domínio (versão estrita)
        if any(ord(c) > 127 for c in domain):
            raise EmailNotValidError("Domínio com caracteres inválidos.")

        dns_ok = _has_mx_or_a_or_parent(domain)

        if dns_ok is False:
            # Domínio realmente sem MX/A (nem no pai)
            gr.Warning("⚠️ O domínio do e-mail informado não aceita mensagens. Confira se está correto.")
            return gr.update(value="", elem_classes=["erro"])
        elif dns_ok is None:
            # Timeout/sem resposta do DNS → não reprovar, apenas aceitar sintaxe ok
            # (Se preferir avisar discretamente, adicione um Warning leve)
            return gr.update(value=addr, elem_classes=[])

        # Tudo certo
        return gr.update(value=addr, elem_classes=[])

    except EmailNotValidError:
        gr.Warning("⚠️ O endereço de e-mail informado não é válido. Verifique se está escrito corretamente (sem acentos) e tente novamente.")
        return gr.update(value="", elem_classes=["erro"])


def _apenas_digitos(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def _valida_cpf(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    soma = sum(int(d[i]) * (10 - i) for i in range(9))
    dv1 = (soma * 10) % 11
    dv1 = 0 if dv1 == 10 else dv1
    if dv1 != int(d[9]): return False
    soma = sum(int(d[i]) * (11 - i) for i in range(10))
    dv2 = (soma * 10) % 11
    dv2 = 0 if dv2 == 10 else dv2
    return dv2 == int(d[10])

def _valida_cnpj(d: str) -> bool:
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    pes2   = [6] + pesos1
    s1 = sum(int(d[i])*pesos1[i] for i in range(12))
    r1 = 11 - (s1 % 11); r1 = 0 if r1 >= 10 else r1
    if r1 != int(d[12]): return False
    s2 = sum(int(d[i])*pes2[i] for i in range(13))
    r2 = 11 - (s2 % 11); r2 = 0 if r2 >= 10 else r2
    return r2 == int(d[13])

def _formata_cpf(d: str) -> str:
    return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"

def _formata_cnpj(d: str) -> str:
    return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"

def validar_cnpj_cpf(valor: str):
    d = _apenas_digitos(valor)
    # vazio → não mexe (deixa o usuário digitar)
    if not d:
        return gr.update(value="", elem_classes=[])

    if len(d) == 11:
        if _valida_cpf(d):
            return gr.update(value=_formata_cpf(d), elem_classes=[])
        else:
            gr.Warning("⚠️ CPF inválido. Preencha no formato 000.000.000-00")
            return gr.update(value="", elem_classes=["erro"])

    if len(d) == 14:
        if _valida_cnpj(d):
            return gr.update(value=_formata_cnpj(d), elem_classes=[])
        else:
            gr.Warning("⚠️ CNPJ inválido. Preencha no formato 00.000.000/0000-00")
            return gr.update(value="", elem_classes=["erro"])

    # tamanho inesperado
    gr.Warning("⚠️ Número inválido. Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).")
    return gr.update(value="", elem_classes=["erro"])

def validar_cpf(valor: str):
    d = _apenas_digitos(valor)
    # vazio → não mexe (deixa o usuário digitar)
    if not d:
        return gr.update(value="", elem_classes=[])
    
    if len(d) == 11:
        if _valida_cpf(d):
            return gr.update(value=_formata_cpf(d), elem_classes=[])
        else:
            gr.Warning("⚠️ CPF inválido. Preencha no formato 000.000.000-00")
            return gr.update(value="", elem_classes=["erro"])
    
     # tamanho inesperado
    gr.Warning("⚠️ Número inválido. Informe um CPF (11 dígitos).")
    return gr.update(value="", elem_classes=["erro"])

def validar_horas_semanais(valor: str):
    if not valor or not str(valor).strip():
        return gr.update(value="", elem_classes=[])

    try:
        # Normaliza separadores
        txt = valor.lower().replace("h", ":").replace("min", "").replace(" ", "")
        txt = txt.replace(",", ".")  # aceita vírgula decimal

        horas, minutos = 0, 0

        if ":" in txt:  # formato hh:mm
            partes = txt.split(":")
            horas = int(partes[0])
            minutos = int(partes[1]) if len(partes) > 1 and partes[1] else 0
        elif "." in txt:  # formato decimal, ex: 22.5
            horas_float = float(txt)
            horas = int(horas_float)
            minutos = round((horas_float - horas) * 60)
        else:  # só horas inteiras
            horas = int(txt)

        total_horas = horas + minutos / 60.0

    except Exception:
        gr.Warning("⚠️ Informe o valor em formato válido (ex: 30h, 22h30min, 22:30 ou 22,5).")
        return gr.update(value="", elem_classes=["erro"])

    if total_horas > 40:
        gr.Warning("⚠️ Horas semanais não pode ultrapassar 40.")
        return gr.update(value="", elem_classes=["erro"])

    # Formata saída sempre como hh:mm
    return gr.update(value=f"{int(horas)}h{minutos:02d}min" if minutos else f"{int(horas)}h", elem_classes=[])


def limpar_erro_quando_digitar(valor: str):
    return gr.update(elem_classes=[])


def converter_valor(valor_str):
    try:
        # Remove 'R$', espaços e outros caracteres não numéricos, exceto vírgula e ponto
        valor_str = re.sub(r"[^\d,\.]", "", valor_str)
        valor_str = valor_str.replace(",", ".").strip()
        valor_float = float(valor_str)
        
        # Separa parte inteira (reais) e decimal (centavos)
        reais = int(valor_float)
        centavos = round((valor_float - reais) * 100)

        partes = []

        if reais > 0:
            partes.append(num2words(reais, lang='pt_BR') + (" real" if reais == 1 else " reais"))
        if centavos > 0:
            partes.append(num2words(centavos, lang='pt_BR') + (" centavo" if centavos == 1 else " centavos"))

        if not partes:
            return "Zero real"

        return " e ".join(partes).capitalize()
    except Exception as e:
        print(f"Erro na conversão do valor: {e}")
        return ""

def calcular_total_dias(data_inicio, data_termino):
    # Verifica se os campos estão preenchidos
    if not data_inicio or not data_termino:
        return gr.update(value="")

    try:
        # Tenta converter as datas
        dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_termino = datetime.strptime(data_termino, "%Y-%m-%d")
        dias = (dt_termino - dt_inicio).days

        # Validação: término antes do início
        if dias < 0:
            gr.Warning("A data de término não pode ser anterior à data de início.")
            return gr.update(value="")

        return f"{dias} dias"
    except ValueError:
        # Formato inválido (ou campos incompletos)
        return gr.update(value="")

# === Função principal ===
def processar_formulario(*args):
    # ------------------------------
    # 1) Campos FIXOS (até "horario_atividades")
    #    -> Deixe essa lista exatamente nessa ordem,
    #       pois é a ordem em que você coloca os inputs antes do *atividades
    nomes_fixos = [
        "tipo_estagio", "razao_social", "cnpj", "nome_fantasia", "endereco", "bairro",
        "cep", "complemento", "cidade", "uf", "email", "telefone",
        "representante", "cpf_repr", "nome_estudante", "nascimento", "cpf_estudante", "rg",
        "endereco_estudante", "bairro_estudante", "cep_estudante", "complemento_estudante",
        "cidade_estudante", "uf_estudante", "email_estudante", "telefone_estudante", "curso_estudante",
        "ano_periodo", "matricula", "orientador", "data_inicio", "data_termino", "total_dias",
        "horas_diarias", "horas_semana_estagio", "total_horas_estagio",
        "seguradora", "apolice",
        "modalidade_estagio", "remunerado", "valor_bolsa", "valor_extenso",
        "auxilio_transporte", "especificacao_auxilio",
        "contraprestacao", "especificacao_contraprestacao",
        "horas_diarias_plano", "horas_semanais_plano", "total_horas_plano",
        "horario_atividades",   # <- último fixo antes das atividades
    ]

    # 2) Campos do "rodapé" (após TODAS as atividades)
    nomes_final = ["nome_supervisor", "formacao_supervisor", "cargo_supervisor", "registro_conselho"]

    num_fixos = len(nomes_fixos)
    num_finais = len(nomes_final)
    total_args = len(args)
    n_atividades = max(0, total_args - (num_fixos + num_finais))

    nomes_completos = (
        nomes_fixos
        + [f"atividade_{i}" for i in range(1, n_atividades + 1)]
        + nomes_final
    )

    # === Aqui está o "desempacotamento" elegante ===
    dados = dict(zip(nomes_completos, args))

    # Agora você acessa qualquer campo por nome:
    # exemplo:
    # tipo_estagio = dados["tipo_estagio"]
    # razao_social = dados["razao_social"]
    # ...
    atividades = [dados[n] for n in nomes_completos if n.startswith("atividade_")]


    # Lista de índices obrigatórios
#     indices_obrigatorios = [
#         0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11,           # empresa
#         12, 13, 14, 15, 16, 17, 18, 19, 20,          # estudante
#         22, 23, 24, 25, 26,                          # estudante continuação
#         27, 28, 29,                                  # acadêmicos
#         30, 31, 32,                                  # datas
#         33, 34, 35,                                  # horários
#         36, 37,                                      # seguradora, apólice
#         38, 39, 40, 41,                              # remuneração
#         42, 44,                                      # auxilio e contraprestação
#         46, 47, 48, 49,                              # plano de atividades
#         61, 62                                       # nome_supervisor, formacao_supervisor
#     ]

    campos_obrigatorios = {
        "tipo_estagio": "Tipo de Estágio",
        "razao_social": "Razão Social",
        "cnpj": "CNPJ",
        "nome_fantasia": "Nome Fantasia",
        "endereco": "Endereço",
        "bairro": "Bairro",
        "cep": "CEP",
        "cidade": "Cidade",
        "uf": "UF",
        "email": "E-mail",
        "telefone": "Telefone",
        "representante": "Representante Legal",
        "cpf_repr": "CPF do Representante Legal",
        "nome_estudante": "Nome do(a) Estudante",
        "nascimento": "Data de Nascimento",
        "cpf_estudante": "CPF do(a) Estudante",
        "rg": "RG",
        "endereco_estudante": "Endereço do(a) Estudante",
        "bairro_estudante": "Bairro do(a) Estudante",
        "cep_estudante": "CEP do(a) Estudante",
        "cidade_estudante": "Cidade do(a) Estudante",
        "uf_estudante": "UF do(a) Estudante",
        "email_estudante": "E-mail do(a) Estudante",
        "telefone_estudante": "Telefone do(a) Estudante",
        "curso_estudante": "Curso do(a) Estudante",
        "ano_periodo": "Ano/Período Letivo",
        "matricula": "Matrícula",
        "orientador": "Professor(a) Orientador(a)",
        "data_inicio": "Data de Início",
        "data_termino": "Data de Término",
        "total_dias": "Total de Dias de Estágio",
        "horas_diarias": "Horas Diárias",
        "horas_semana_estagio": "Horas Semanais de Estágio",
        "total_horas_estagio": "Total de Horas de Estágio",
        "seguradora": "Nome da Seguradora",
        "apolice": "Nº da Apólice de Seguro",
        "modalidade_estagio": "Modalidade do Estágio",
        "remunerado": "Remunerado",
        "auxilio_transporte": "Auxílio Transporte",
        "contraprestacao": "Contraprestação de Serviços",
        "horas_diarias_plano": "Horas Diárias no Plano",
        "horas_semanais_plano": "Horas Semanais no Plano",
        "total_horas_plano": "Total de Horas no Plano",
        "horario_atividades": "Horário das Atividades",
        "nome_supervisor": "Nome do(a) Supervisor(a)",
        "cargo_supervisor": "Cargo/Função do(a) Supervisor(a) no(a) concedente",
        "formacao_supervisor": "Formação do(a) Supervisor(a)"
    }
    

    # Desempacotamento
#     (
#         tipo_estagio, razao_social, cnpj, nome_fantasia, endereco, bairro,
#         cep, complemento, cidade, uf, email, telefone,
#         representante, cpf_repr, nome_estudante, nascimento, cpf_estudante, rg,
#         endereco_estudante, bairro_estudante, cep_estudante, complemento_estudante,
#         cidade_estudante, uf_estudante, email_estudante, telefone_estudante, curso_estudante,
#         ano_periodo, matricula, orientador, data_inicio, data_termino, total_dias,
#         horas_diarias, horas_semana_estagio, total_horas_estagio,
#         seguradora, apolice,
#         modalidade_estagio, remunerado, valor_bolsa, valor_extenso,
#         auxilio_transporte, especificacao_auxilio,
#         contraprestacao, especificacao_contraprestacao,
#         horas_diarias_plano, horas_semanais_plano, total_horas_plano,
#         horario_atividades,
#         atividade_1, atividade_2, atividade_3, atividade_4, atividade_5,
#         atividade_6, atividade_7, atividade_8, atividade_9, atividade_10,
#         nome_supervisor, formacao_supervisor, cargo_supervisor, registro_conselho
#     ) = args
    
    
    # Validação de obrigatórios (realça apenas os que faltam e preserva os demais)
    # --- PREPARE: lista de updates + helper de marcação ---
    updates = [gr.update(value=v, elem_classes=[]) for v in args]

    def marcar_erro(nome, on=True):
        idx = nomes_completos.index(nome)
        val_atual = args[idx]
        updates[idx] = gr.update(value=val_atual, elem_classes=(["erro"] if on else []))

    # =========================
    # 1) Regras condicionais primeiro
    # =========================
    remunerado    = dados["remunerado"]
    valor_bolsa   = dados["valor_bolsa"]
    valor_extenso = dados["valor_extenso"]

    if remunerado == "Sim":
        if not str(valor_bolsa or "").strip():
            marcar_erro("valor_bolsa", True)
            gr.Warning("⚠️ O campo 'Valor da Bolsa' é obrigatório para a opção remunerado 'Sim'.")
            return updates
        if not str(valor_extenso or "").strip():
            marcar_erro("valor_extenso", True)
            gr.Warning("⚠️ O campo 'Valor por Extenso' é obrigatório para a opção remunerado 'Sim'.")
            return updates
    # limpa borda se corrigiu
    marcar_erro("valor_bolsa", False)
    marcar_erro("valor_extenso", False)

    auxilio_transporte    = dados["auxilio_transporte"]
    especificacao_auxilio = dados["especificacao_auxilio"]
    if auxilio_transporte == "Sim":
        if not str(especificacao_auxilio or "").strip():
            marcar_erro("especificacao_auxilio", True)
            gr.Warning("⚠️ O campo 'Especificação do Auxílio Transporte' é obrigatório para a opção Sim.")
            return updates
    marcar_erro("especificacao_auxilio", False)

    contraprestacao                 = dados["contraprestacao"]
    especificacao_contraprestacao   = dados["especificacao_contraprestacao"]
    if contraprestacao == "Sim":
        if not str(especificacao_contraprestacao or "").strip():
            marcar_erro("especificacao_contraprestacao", True)
            gr.Warning("⚠️ O campo 'Especificação da Contraprestação' é obrigatório para a opção Sim.")
            return updates
    marcar_erro("especificacao_contraprestacao", False)

    # =========================
    # 2) Obrigatórios gerais
    # =========================
    erros_rotulos = []
    for idx, nome in enumerate(nomes_completos[:len(args)]):
        obrigatorio = nome in campos_obrigatorios
        valor = args[idx]
        vazio = (valor is None) or (str(valor).strip().lower() in ["", "none"])
        if obrigatorio and vazio:
            marcar_erro(nome, True)
            erros_rotulos.append(campos_obrigatorios[nome])
        else:
            marcar_erro(nome, False)

    if erros_rotulos:
        lista = ", ".join(erros_rotulos[:4]) + ("..." if len(erros_rotulos) > 4 else "")
        gr.Warning(f"⚠️ Preencha os campos obrigatórios destacados em vermelho: {lista}.")
        return updates

    # =========================
    # 3) Datas com borda vermelha
    # =========================
    data_inicio  = dados["data_inicio"]
    data_termino = dados["data_termino"]
    nascimento   = dados["nascimento"]

    faltou_i = not data_inicio
    faltou_t = not data_termino
    faltou_n = not nascimento

    if faltou_i or faltou_t:
        if faltou_i: marcar_erro("data_inicio", True)
        if faltou_t: marcar_erro("data_termino", True)
        gr.Warning("⚠️ Você precisa informar a data de início e a data de término do estágio.")
        return updates

    if faltou_n:
        marcar_erro("nascimento", True)
        gr.Warning("⚠️ O campo 'Data de Nascimento' é obrigatório.")
        return updates

    try:
        dt_inicio     = datetime.strptime(data_inicio,  "%Y-%m-%d")
        dt_termino    = datetime.strptime(data_termino, "%Y-%m-%d")
        dt_nascimento = datetime.strptime(nascimento,   "%Y-%m-%d")
    except ValueError:
        marcar_erro("data_inicio", True)
        marcar_erro("data_termino", True)
        marcar_erro("nascimento", True)
        gr.Warning("⚠️ Formato inválido de data. Use o seletor de calendário.")
        return updates

    if dt_termino < dt_inicio:
        marcar_erro("data_inicio", True)
        marcar_erro("data_termino", True)
        gr.Warning("⚠️ A data de término não pode ser anterior à data de início.")
        return updates

    # tudo ok nas datas → limpa
    marcar_erro("data_inicio", False)
    marcar_erro("data_termino", False)
    marcar_erro("nascimento", False)

    data_inicio  = dt_inicio.strftime("%d/%m/%Y")
    data_termino = dt_termino.strftime("%d/%m/%Y")
    nascimento   = dt_nascimento.strftime("%d/%m/%Y")

    # (Se você precisa dos formatos dd/mm/aaaa depois, faça a conversão aqui em variáveis locais,
    #   mas NÃO altere args; o 'updates' é só para UI)

    # =========================
    # 4) Atividades (mínimo 5) com borda vermelha
    # =========================
    indices_atividades = [nomes_completos.index(f"atividade_{i}") for i in range(1, 11)]
    valores_atividades = [(i, (str(args[i]).strip() if args[i] is not None else "")) for i in indices_atividades]

    preenchidas = [(i, v) for (i, v) in valores_atividades if v]
    vazias      = [i for (i, v) in valores_atividades if not v]

    if len(preenchidas) < 5:
        faltam = 5 - len(preenchidas)
        for i in vazias[:faltam]:
            updates[i] = gr.update(value=args[i], elem_classes=["erro"])
        gr.Warning(f"⚠️ Informe pelo menos 5 atividades (faltam {faltam}).")
        return updates

    # ------------------------------
    # 6) Se chegou aqui, está tudo OK — siga com o resto do processamento
    # (geração de PDF, prints, etc.)

    print("=== TERMO DE COMPROMISSO DE ESTÁGIO ===")
    print(f"Tipo de Estágio: {dados['tipo_estagio']}")
    print(f"Razão Social: {dados['razao_social']}")
    print(f"CNPJ: {dados['cnpj']}")
    print(f"Nome Fantasia: {dados['nome_fantasia']}")
    print(f"Endereço: {dados['endereco']}")
    print(f"Bairro: {dados['bairro']}")
    print(f"CEP: {dados['cep']}")
    print(f"Complemento: {dados['complemento']}")
    print(f"Cidade: {dados['cidade']}")
    print(f"UF: {dados['uf']}")
    print(f"E-mail: {dados['email']}")
    print(f"Telefone: {dados['telefone']}")
    print(f"Representante: {dados['representante']}")
    print(f"CPF Representante: {dados['cpf_repr']}")
    print(f"Nome do(a) Estudante: {dados['nome_estudante']}")
    print(f"Nascimento: {dados['nascimento']}")
    print(f"CPF do(a) Estudante: {dados['cpf_estudante']}")
    print(f"RG do(a) Estudante: {dados['rg']}")
    print(f"Endereço do(a) Estudante: {dados['endereco_estudante']}")
    print(f"Bairro do(a) Estudante: {dados['bairro_estudante']}")
    print(f"CEP do(a) Estudante: {dados['cep_estudante']}")
    print(f"Complemento do(a) Estudante: {dados['complemento_estudante']}")
    print(f"Cidade do(a) Estudante: {dados['cidade_estudante']}")
    print(f"UF do(a) Estudante: {dados['uf_estudante']}")
    print(f"E-mail do(a) Estudante: {dados['email_estudante']}")
    print(f"Telefone do(a) Estudante: {dados['telefone_estudante']}")
    print(f"Curso do(a) Estudante: {dados['curso_estudante']}")
    print(f"Ano/Período Letivo: {dados['ano_periodo']}")
    print(f"Matrícula: {dados['matricula']}")
    print(f"Orientador(a): {dados['orientador']}")
    print(f"Data de Início: {dados['data_inicio']}")
    print(f"Data de Término: {dados['data_termino']}")
    print(f"Total de Dias de Estágio: {dados['total_dias']}")
    print(f"Horas Diárias: {dados['horas_diarias']}")
    print(f"Horas Semanais de Estágio: {dados['horas_semana_estagio']}")
    print(f"Total de Horas de Estágio: {dados['total_horas_estagio']}")
    print(f"Seguradora: {dados['seguradora']}")
    print(f"Apólice: {dados['apolice']}")
    print(f"Modalidade do Estágio: {dados['modalidade_estagio']}")
    print(f"Remunerado: {dados['remunerado']}")
    print(f"Valor da Bolsa: {dados['valor_bolsa']}")
    print(f"Valor por Extenso: {dados['valor_extenso']}")
    print(f"Auxílio Transporte: {dados['auxilio_transporte']}")
    print(f"Especificação do Auxílio Transporte: {dados['especificacao_auxilio']}")
    print(f"Contraprestação de Serviços: {dados['contraprestacao']}")
    print(f"Especificação da Contraprestação: {dados['especificacao_contraprestacao']}")
    print(f"Horas Diárias no Plano: {dados['horas_diarias_plano']}")
    print(f"Horas Semanais do Plano de Atividades: {dados['horas_semanais_plano']}")
    print(f"Total de Horas do Plano de Atividades: {dados['total_horas_plano']}")
    print(f"Horário das Atividades: {dados['horario_atividades']}")

    
    print("=== ATIVIDADES ===")
    for i, atividade in enumerate(atividades, start=1):
        valor = str(atividade).strip()
        if valor:
            print(f"Atividade {i}: {valor}")

    print("=== SUPERVISOR(A) DO ESTÁGIO ===")
    print(f"Nome do(a) Supervisor(a): {dados['nome_supervisor']}")
    print(f"Formação do(a) Supervisor(a): {dados['formacao_supervisor']}")
    print(f"Cargo/Função do(a) Supervisor(a) no(a) concedente: {dados['cargo_supervisor']}")
    print(f"Registro no Conselho: {dados['registro_conselho']}")

    print("✅ Termo registrado com sucesso!")
    gr.Info("✅ Termo registrado com sucesso!")
    
    
    # Limpa os campos após submissão (se desejar)
    return [None] * len(args)
    

with gr.Blocks(theme="default") as demo:
    # CSS de erro (uma vez na app)
    gr.HTML("""
        <style>
        /* Borda vermelha em inputs de texto/textarea/select */
        .erro input,
        .erro textarea,
        .erro select {
          border-color: #dc2626 !important;
          border-width: 1px !important;
          border-style: solid !important;
          box-shadow: 0 0 0 1px #dc2626 inset !important;
        }

        /* Mantém o vermelho mesmo com foco */
        .erro input:focus,
        .erro textarea:focus,
        .erro select:focus {
          border-color: #dc2626 !important;
          box-shadow: 0 0 0 1px #dc2626 inset !important;
        }

        /* Fallback para componentes não-input (ex.: Radio/Checkbox) */
        .erro {
          outline: 2px solid #dc2626 !important;
          outline-offset: 2px;
          border-radius: 6px;
        }
        </style>
        """)
    
    gr.HTML("""
        <style>
        /* Sinaliza ao Google Translate para não mexer nesses elementos */
        .notranslate, .notranslate * { translate: none; } /* inibe tradutores */
        </style>
        """)
    
     # CSS anti-erro (se já não tiver)
    gr.HTML("""
    <style>
    .erro select {              /* dropdown */
      border-color:#dc2626!important; box-shadow:0 0 0 1px #dc2626 inset!important;
    }
    </style>
    """)
    
    gr.Markdown("<h2 style='text-align: center;'>TERMO DE COMPROMISSO DE ESTÁGIO</h2>")
    
    gr.Markdown("(*) Preenchimento obrigatório")

    tipo_estagio = gr.Radio(
        choices=["CURRICULAR OBRIGATÓRIO", "NÃO OBRIGATÓRIO"],
        label="Tipo de Estágio*",
        value=None
    )

    gr.Markdown("**Instrumento Jurídico de Termo de Compromisso de Estágio, sem vínculo empregatício, de que trata o art. 7º, inciso I da lei nº 11.788/2008.**")
    
    gr.Markdown("Este termo tem de um lado,")
    
    gr.Markdown("### DADOS DO(A) CONCEDENTE")

    with gr.Row(equal_height=True):
        with gr.Column(scale=1, min_width=0):
            razao_social = gr.Text(label="Razão Social*", placeholder="Ex: Empresa Exemplo Ltda")
        with gr.Column(scale=1, min_width=0):
            cnpj = gr.Text(
                label="CNPJ (00.000.000/0000-00) ou CPF (000.000.000-00)*",
                placeholder="Ex: 12.345.678/0001-99 ou 123.456.789-00"
            )
            
    # valida ao sair do campo
    cnpj.blur(validar_cnpj_cpf, inputs=cnpj, outputs=cnpj)

    # linha seguinte com largura total
    nome_fantasia = gr.Text(
        label="Nome Fantasia*",
        placeholder="",
    )

    with gr.Row():
        endereco = gr.Text(label="Endereço*")
        bairro = gr.Text(label="Bairro*")
        cep = gr.Text(label="CEP (00000-000)*", placeholder="Ex: 12345-000")
    
    
    UF_OPCOES = [
        "AC","AL","AM","AP","BA","CE","DF","ES","GO","MA",
        "MG","MS","MT","PA","PB","PE","PI","PR","RJ","RN",
        "RO","RR","RS","SC","SE","SP","TO"
    ]

    def validar_uf(valor: str):
        if valor in UF_OPCOES:
            # ok, remove borda vermelha
            return gr.update(value=valor, elem_classes=[])
        else:
            gr.Warning("⚠️ UF inválida. Selecione uma das opções da lista.")
            return gr.update(value=None, elem_classes=["erro"])
    
    with gr.Row():
        complemento = gr.Text(label="Complemento")
        cidade = gr.Text(label="Cidade*")
        uf = gr.Dropdown(
            label="UF*",
            choices=UF_OPCOES,
            value=None,
            type="value",
            interactive=True,
            elem_classes=["notranslate"]
        )
    
    uf.blur(validar_uf, inputs=uf, outputs=uf)
    
    with gr.Row():
        email = gr.Textbox(label="E-mail*", placeholder="exemplo@dominio.com")
        telefone = gr.Text(label="Telefone (00) 00000-0000*", placeholder="Ex: (64) 91234-5678")
    
    email.blur(validar_email_estrito, inputs=email, outputs=email)

    with gr.Row():
        representante = gr.Text(label="Representante legal*")
        cpf_repr = gr.Text(label="CPF (000.000.000-00)*", placeholder="Ex: 123.456.789-00")
    
    cpf_repr.blur(validar_cpf, inputs=cpf_repr, outputs=cpf_repr)
    
    gr.Markdown("Do outro lado o(a) estudante,")
    
    gr.Markdown("### DADOS DO(A) ESTUDANTE")

    nome_estudante = gr.Text(label="Nome*")
    
    with gr.Row():
        # Campo visual com seletor de data
        gr.HTML("""
        <label for="input-nascimento">Data de Nascimento (use o seletor abaixo)*</label><br>
        <input type="date" id="input-nascimento" onchange="
            const txt = document.querySelector('#nascimento textarea');
            txt.value = this.value;
            txt.dispatchEvent(new Event('input', { bubbles: true }));
        ">
        """)

        # Campo oculto que receberá o valor real
        nascimento = gr.Textbox(elem_id="nascimento", visible=False)

        cpf_estudante = gr.Textbox(
            label="CPF (000.000.000-00)*",
            placeholder="Ex: 123.456.789-00"
        )

        rg = gr.Text(label="RG*")
    
    # valida ao sair do campo (estudante) — reutiliza a MESMA função
    cpf_estudante.blur(validar_cpf, inputs=cpf_estudante, outputs=cpf_estudante)
        
    with gr.Row():
        endereco_estudante = gr.Text(label="Endereço*")
        bairro_estudante = gr.Text(label="Bairro*")
        cep_estudante = gr.Text(label="CEP (00000-000)*", placeholder="Ex: 12345-000")
    
    with gr.Row():
        complemento_estudante = gr.Text(label="Complemento")
        cidade_estudante = gr.Text(label="Cidade*")
        uf_estudante = gr.Dropdown(
            label="UF*",
            choices=UF_OPCOES,
            value=None,
            type="value",
            interactive=True,
            elem_classes=["notranslate"]
        )
    
    uf_estudante.blur(validar_uf, inputs=uf_estudante, outputs=uf_estudante)
    
    with gr.Row():
        email_estudante = gr.Textbox(label="E-mail do Estudante*", placeholder="exemplo@dominio.com")
        telefone_estudante = gr.Text(label="Telefone (00) 00000-0000)*", placeholder="Ex: (64) 91234-5678")
    
    email_estudante.blur(validar_email_estrito, inputs=email_estudante, outputs=email_estudante)
    
    CURSO_OPCOES = [
        "Bacharelado em Administração",
        "Bacharelado em Zootecnia",
        "Técnico em Agropecuária",
        "Técnico em Administração",
        "Técnico em Informática",
    ]

    def validar_curso(valor: str):
        if valor in CURSO_OPCOES:
            return gr.update(value=valor, elem_classes=[])   # ok
        else:
            gr.Warning("⚠️ Curso inválido. Selecione uma opção da lista.")
            return gr.update(value=None, elem_classes=["erro"])


    curso_estudante = gr.Dropdown(
        label="Curso*",
        choices=CURSO_OPCOES,
        value=None,
        type="value",
        interactive=True,
        elem_classes=["notranslate"]   # ver item 2
    )

    curso_estudante.blur(validar_curso, inputs=curso_estudante, outputs=curso_estudante)

    with gr.Row():
        ano_periodo = gr.Dropdown(
            label="Ano/Período do Curso*",
            choices=[str(i) for i in range(1, 11)],  # gera de "1" a "10"
            type="value",
            value=None,       # começa vazio
            allow_custom_value=False,  # impede digitar manualmente
            interactive=True
        )

        matricula = gr.Text(label="Número de Matrícula*")

    orientador = gr.Text(label="Professor(a) orientador(a)*")
    
    # Use HTML inline dentro do Markdown só nos nomes próprios
    gr.Markdown("""
    ambos com a interveniência do **INSTITUTO FEDERAL GOIANO - CAMPUS CAMPOS BELOS**,\
    situado à Rodovia GO118, Km 341, Setor Novo Horizonte, em Campos Belos – GO, CEP.73.840.000,\
    inscrito no CNPJ de n.º 10.651.417/0012-20, neste ato representado pelo Diretor-Geral,\
    **<span class="notranslate">Prof. Althiéris de Souza Saraiva</span>** (**Portaria N.º 1.653 REI/IFGOIANO,\
    de 14/03/2024, D.O.U de 15/03/2024**) e pelo coordenador de Extensão,\
    **<span class="notranslate">Prof.º João Rufino Junior</span>** (**Portaria N.º 1.086, D.O.U. de 06/12/2018**),\
    celebram entre si este termo, convencionado às cláusulas e condições seguintes:
   
    ### CLÁUSULA PRIMEIRA – DO OBJETO
    Este **TERMO** tem por objeto formalizar as condições para a realização de **ESTÁGIOS** de Estudantes, como forma de complementação do processo de ensino – aprendizagem, nos termos e condições da Lei 11.788/08 e pelas normas de estágio do Instituto Federal Goiano.

    ### CLÁUSULA SEGUNDA – DA DURAÇÃO
    Este **TERMO** terá vigência conforme descrito na tabela abaixo, podendo ser rescindido unilateralmente por qualquer das partes, a qualquer momento, sem ônus, multas, mediante comunicação feita por escrito, com, no mínimo, cinco dias de antecedência:
    """, elem_classes=["notranslate"])
    
    with gr.Row():
#         data_inicio = gr.Text(
#             label="Data de Início (dd/mm/aaaa)",
#             placeholder="Ex: 12/05/2025"
#         )

#         data_termino = gr.Text(
#             label="Data de Término (dd/mm/aaaa)",
#             placeholder="Ex: 07/07/2025"
#         )
       
         # Inputs de data visuais (com calendário)
       # Inputs de data visuais (com calendário)
        gr.HTML("""
        <label for="input-inicio">Data de Início (use o seletor abaixo)*</label><br>
        <input type="date" id="input-inicio" onchange="
            const txt = document.querySelector('#data_inicio textarea');
            txt.value = this.value;
            txt.dispatchEvent(new Event('input', { bubbles: true }));
        ">
        """)
        gr.HTML("""
        <label for="input-termino">Data de Término (use o seletor abaixo)*</label><br>
        <input type="date" id="input-termino" onchange="
            const txt = document.querySelector('#data_termino textarea');
            txt.value = this.value;
            txt.dispatchEvent(new Event('input', { bubbles: true }));
        ">
        """)
        
         # Inputs ocultos
        data_inicio = gr.Textbox(elem_id="data_inicio", visible=False)
        data_termino = gr.Textbox(elem_id="data_termino", visible=False)

        # Campo automático de total de dias
        total_dias = gr.Text(
            label="Total de dias previstos para estágio",
            placeholder="Ex: 40 dias",
            interactive=False
        )

        # Atualiza o total de dias automaticamente
        data_inicio.change(fn=calcular_total_dias, inputs=[data_inicio, data_termino], outputs=total_dias)
        data_termino.change(fn=calcular_total_dias, inputs=[data_inicio, data_termino], outputs=total_dias) 
        
#         total_dias = gr.Text(
#             label="Total de dias previstos para estágio",
#             placeholder="Ex: 40 dias"
#         )
        

    gr.Markdown("""
        **Parágrafo único.** O Estagiário terá direito a recesso de 30 (trinta) dias, compatíveis com suas férias escolares, sempre que o estágio tenha duração igual ou superior a 1 (um) ano. Sendo proporcional o recesso, em casos de estágio inferior a 1 (um) ano.

        ### CLÁUSULA TERCEIRA – DO VÍNCULO
        O estágio, tanto obrigatório quanto o não obrigatório, não cria vínculo empregatício de qualquer natureza, desde que observados os termos do art. 3º da Lei nº 11.788/2008 e as disposições do presente Termo.

        ### CLÁUSULA QUARTA – DA CARGA HORÁRIA
        A carga horária do Estágio será cumprida conforme apresentado na tabela abaixo, em consonância ao art. 10 da Lei nº 11.788/2008:
        """)
    
    with gr.Row():
        horas_diarias = gr.Radio(
            choices=[str(i) for i in range(1, 9)],
            label="Horas diárias (marque o valor correspondente)*",
            info="Selecione de 1 a 8 horas",
            container=True
        )
        horas_semana_estagio = gr.Text(
            label="Horas semanais (máximo 40 h/s)*",
            placeholder="Ex: 30h",
            value=None
        )
        total_horas_estagio = gr.Text(
            label="Total de horas do estágio*",
            placeholder="Ex: 240 horas",
            value=None
        )
    
    # valida quando perde o foco
        horas_semana_estagio.blur(
            validar_horas_semanais, 
            inputs=horas_semana_estagio, 
            outputs=horas_semana_estagio
        )
        
    gr.Markdown("""
        § 1º - À Unidade Concedente caberá fixação de horário e local do estágio, expressos na respectiva programação, que o(a) Estagiário(a) se obriga a cumprir fielmente, desde que não prejudique o cumprimento de suas obrigações escolares, comunicando em tempo hábil, a impossibilidade de fazê-lo.

        § 2º – A Instituição de Ensino comunicará à parte concedente do estágio, através do estudante, as datas de realização de avaliações escolares ou acadêmicas.

        § 3º – Nos períodos de avaliação escolar ou acadêmica, a carga horária do estágio será reduzida pelo menos à metade, para garantir o bom desempenho do estudante.
        """)
    
    gr.Markdown("""
        ### CLÁUSULA QUINTA – DAS OBRIGAÇÕES

        **Compete à Instituição de Ensino:**
        1. Celebrar TCE com o(a) concedente e estagiário(a) para fins de Estágio com interveniência do Instituto Federal Goiano – Campus Campos Belos;  
        2. Avaliar as instalações da parte concedente do estágio e sua adequação à formação cultural e profissional do educando;  
        3. Indicar professor orientador, da área do estágio, como responsável pelo acompanhamento das atividades do estagiário, o qual deverá opor visto nos relatórios de atividades desenvolvidas no estágio;  
        4. Exigir do educando e do(a) CONCEDENTE a apresentação periódica, em prazo não superior a 6 (seis) meses, de relatório de atividades desenvolvidas.  

        **Compete ao Estagiário:**
        1. Celebrar TCE com o(a) concedente para fins de Estágio com interveniência do Instituto Federal Goiano – Campus Campos Belos;  
        2. Comunicar à instituição de ensino qualquer anormalidade na realização do estágio;  
        3. Cumprir as atividades relacionadas no programa de estágio, descritas neste TCE;  
        4. Cumprir os horários de estágio, comunicando, em tempo hábil, impossibilidade de fazê-lo, por incompatibilidade com as atividades escolares ou outras que justifiquem a impossibilidade de comparecimento;  
        5. O(A) estagiário(a) também se obriga a elaborar o relatório final de estágio, a ser entregue na coordenação de curso a qual está vinculado(a), na data estipulada, discriminando as atividades realizadas.  

        **Compete à Unidade Concedente:**
        1. Celebrar TCE com o(a) estudante para fins de Estágio com interveniência do Instituto Federal Goiano – Campus Campos Belos;  
        2. Disponibilizar instalações que tenham condições de proporcionar ao estagiário atividades de aprendizagem social, profissional e cultural;  
        3. Indicar funcionário de seu quadro de pessoal, com formação ou experiência profissional na área de conhecimento desenvolvida no curso do estagiário para, supervisionar no máximo 10 (dez) estagiários;  
        4. Manter à disposição da fiscalização documentos que comprovem a relação de estágio;  
        5. Enviar à instituição de ensino, com periodicidade mínima de 6 (seis) meses, ou em caso de desligamento, ou ainda, na rescisão antecipada deste termo, relatório de atividades contendo indicação resumida das atividades desenvolvidas, dos períodos efetivados e da avaliação de desempenho, com visto obrigatório do estagiário;  
        6. Manter os estagiários sujeitos às normas relacionadas à saúde e segurança no trabalho;  
        7. Informar à Instituição de Ensino quaisquer necessidades de alteração no TCE firmado.
        """)

    
    gr.Markdown("""
        ### CLÁUSULA SEXTA – DO SEGURO
        Na vigência do presente **TERMO**, o estagiário estará incluído na cobertura de Seguro Contra Acidentes Pessoais conforme apresentado na tabela abaixo:
        """)
    
    with gr.Row():
        seguradora = gr.Text(label="Nome da Seguradora*", placeholder="Ex: MAPFRE Seguros")
        apolice = gr.Text(label="Nº da Apólice de Seguro*", placeholder="Ex: 1234567890123")
    
    gr.Markdown("""
        ### CLÁUSULA SÉTIMA – DOS BENEFÍCIOS  
        O estagiário poderá receber bolsa ou outra forma de contraprestação que venha a ser acordada, conforme apresentado na tabela abaixo, sendo compulsória a sua concessão, bem como a do auxílio transporte, na hipótese de estágio não obrigatório.
        """)
    
    
    with gr.Group():
        gr.Markdown("**DADOS DO(S) BENEFÍCIO(S)**")

        modalidade_estagio = gr.Radio(
            label="Modalidade do Estágio*",
            choices=["Curricular Obrigatório", "Não Obrigatório"],
            value=None,
            interactive=False  # impede edição direta pelo usuário
        )
        
        # Função que sincroniza os valores
        def atualizar_modalidade(tipo):
            if tipo == "CURRICULAR OBRIGATÓRIO":
                return gr.update(value="Curricular Obrigatório")
            elif tipo == "NÃO OBRIGATÓRIO":
                return gr.update(value="Não Obrigatório")
            return gr.update(value=None)

        # Conectar alteração do tipo ao campo modalidade
        tipo_estagio.change(
            fn=atualizar_modalidade,
            inputs=[tipo_estagio],
            outputs=[modalidade_estagio]
        )

        remunerado = gr.Radio(
            label="O estágio é remunerado?*",
            choices=["Sim", "Não"],
            value=None
        )

        valor_bolsa = gr.Text(
            label="Valor da bolsa (R$)*", 
            placeholder="Ex: 500,00"
        )

        valor_extenso = gr.Text(
            label="Valor da remuneração por extenso*", 
            interactive=False
        )
        
        valor_bolsa.change(
            converter_valor, 
            inputs=valor_bolsa, 
            outputs=valor_extenso
        )

        auxilio_transporte = gr.Radio(
            label="A CONCEDENTE fornece auxílio transporte?*",
            choices=["Sim", "Não"]
        )

        especificacao_auxilio = gr.Text(
            label="Se SIM, especifique (Ex: próprio pela CONCEDENTE, dinheiro, vale-transporte, etc.)",
            placeholder="Ex: Vale-transporte"
        )

        contraprestacao = gr.Radio(
            label="Há contraprestação?*",
            choices=["Sim", "Não"]
        )

        especificacao_contraprestacao = gr.Text(
            label="Se SIM, especifique a contraprestação",
            placeholder="Ex: Ajuda de custo mensal"
        )
        
    gr.Markdown("""
        **Parágrafo único.** As atividades de estágio, assim como, a eventual concessão de benefícios relacionados à transporte, alimentação e saúde, entre outros benefícios, não caracterizam vínculo empregatício de qualquer natureza entre o estagiário e a concedente, de acordo com o Art. 3º da Lei 11.788/2008.

        ### CLÁUSULA OITAVA – DA RESCISÃO
        O presente **TERMO** será rescindido automaticamente quando:
        a) Ao término do período de vigência informado na CLÁUSULA SEGUNDA;  
        b) Desistência do(a) Estagiário(a);  
        c) Unilateralmente por qualquer das partes, a qualquer momento, sem ônus, multas, mediante comunicação feita por escrito, com cinco dias de antecedência, no mínimo;  
        d) Do trancamento da matrícula, abandono, desligamento ou conclusão do curso;  
        e) Do descumprimento das condições do presente termo.
        """)

    gr.Markdown("""
    ### CLÁUSULA NONA – PLANO DE ATIVIDADES DE ESTÁGIO
    """)
    
#     horas_diarias_plano = gr.Radio(
#         label="Horas diárias (marque o valor correspondente)*", 
#         choices=[str(i) for i in range(1, 9)], 
#         type="value"
#     )
    
    # Radio do plano (preenchido automaticamente, sem edição)
    horas_diarias_plano = gr.Radio(
        label="Horas diárias (plano)*",
        choices=[str(i) for i in range(1, 9)],
        type="value",
        value=None,
        interactive=False   # impede edição manual
    )

    # 3) Função de sincronização
    def sincronizar_horas_diarias(v):
        # Se limpar/voltar a None, apaga o espelho também
        if not v:
            return gr.update(value=None)
        # Garante string
        return gr.update(value=str(v))

    # 4) Liga os componentes
    horas_diarias.change(
        sincronizar_horas_diarias,
        inputs=horas_diarias,
        outputs=horas_diarias_plano
    )

    with gr.Row():
        horas_semanais_plano = gr.Text(
            label="Horas semanais*",
            placeholder="Ex: 30h",
            value=None,
            interactive=False   # impede edição manual
        )
        def sincronizar_horas_semanais(v):
            if not v:  # se vazio, limpa também o espelho
                return gr.update(value=None)
            return gr.update(value=v)

        # Conexão entre os dois campos
        horas_semana_estagio.change(
            sincronizar_horas_semanais,
            inputs=horas_semana_estagio,
            outputs=horas_semanais_plano
        )
        
        # Campo espelhado (apenas exibe, sem edição)
        total_horas_plano = gr.Text(
            label="Total de horas do estágio*",
            placeholder="Ex: 300 horas",
            value=None,
            interactive=False   # impede edição manual
        )
        
        # Função de sincronização
        def sincronizar_total_horas(v):
            if not v:  # se vazio, limpa também o espelho
                return gr.update(value=None)
            return gr.update(value=v)

        # 4) Conexão entre os dois campos
        total_horas_estagio.change(
            sincronizar_total_horas,
            inputs=total_horas_estagio,
            outputs=total_horas_plano
        )
        
        horario_atividades = gr.Text(label="Horário de realização das atividades*", placeholder="Ex: 13h às 17h30min")
    
        
    
    # ==== ATIVIDADES DINÂMICAS (mín. 5, sem máximo prático) ====

    MAX_ATIVIDADES = 30  # pode ajustar se quiser
    MIN_ATIVIDADES = 5

    gr.Markdown("**As seguintes atividades serão desenvolvidas (mínimo de 5 atividades):**")

    with gr.Row():
        btn_add = gr.Button("➕ Adicionar atividade")
        btn_rem = gr.Button("➖ Remover última")

    # Estado: quantas atividades estão visíveis agora
    ativ_count = gr.State(MIN_ATIVIDADES)

    # Pré-cria os campos (Atividade 1..N) e deixa só as 5 primeiras visíveis
    atividades = []
    for i in range(1, MAX_ATIVIDADES + 1):
        atividades.append(
            gr.Text(
                label=f"Atividade {i}",
                placeholder=f"Descreva a atividade {i}",
                visible=(i <= MIN_ATIVIDADES)
            )
        )

    def add_atividade(n):
        # revela mais um até o máximo
        if n < MAX_ATIVIDADES:
            n += 1
        updates = []
        for i in range(MAX_ATIVIDADES):
            # visível se índice < n
            updates.append(gr.update(visible=(i < n)))
        return [n, *updates]

    def rem_atividade(n):
        # esconde a última, mas nunca abaixo do mínimo
        if n > MIN_ATIVIDADES:
            n -= 1
        updates = []
        for i in range(MAX_ATIVIDADES):
            updates.append(gr.update(visible=(i < n)))
        return [n, *updates]

    btn_add.click(add_atividade, inputs=ativ_count, outputs=[ativ_count, *atividades])
    btn_rem.click(rem_atividade, inputs=ativ_count, outputs=[ativ_count, *atividades])

    
    gr.Markdown("""
    **O(A) concedente designará para supervisor(a) do Estágio:**  
    """)
    
    nome_supervisor = gr.Text(label="Nome do(a) Supervisor(a)*", placeholder="Ex: José da Silva")
    formacao_supervisor = gr.Text(label="Formação do(a) Supervisor(a)*", placeholder="Ex: Advogado")
    cargo_supervisor = gr.Text(label="Cargo/Função do(a) Supervisor(a) no(a) concedente*",\
                               placeholder="Ex: Gerente administrativo, Proprietário, etc.")
    registro_conselho = gr.Text(label="Nº do registro no conselho (quando este o exigir)", placeholder="Ex: OAB-TO: 0.000")
    
    gr.Markdown("""
        ### CLÁUSULA DÉCIMA – DO FORO
        O Foro para dirimir as questões oriundas deste instrumento é o da Justiça Federal, Subseção Judiciária de Goiânia – Estado de Goiás, conforme determina o Art. 109, I, da Constituição Federal.

        """)
    

    # Botão de submissão
    botao = gr.Button("Enviar Termo")
    botao.click(
        fn=processar_formulario, 
        inputs=[
            tipo_estagio, razao_social, cnpj, nome_fantasia, endereco, bairro, cep, complemento, cidade, uf, 
            email, telefone, representante, cpf_repr, nome_estudante, nascimento, cpf_estudante, rg, 
            endereco_estudante, bairro_estudante, cep_estudante, complemento_estudante, cidade_estudante, uf_estudante,
            email_estudante, telefone_estudante, curso_estudante, ano_periodo, matricula,
            orientador, data_inicio, data_termino, total_dias, horas_diarias, horas_semana_estagio, total_horas_estagio,
            seguradora, apolice, modalidade_estagio, remunerado, valor_bolsa, valor_extenso, auxilio_transporte,
            especificacao_auxilio, contraprestacao, especificacao_contraprestacao, horas_diarias_plano, horas_semanais_plano,
            total_horas_plano, horario_atividades,
            *atividades,
            nome_supervisor, formacao_supervisor, cargo_supervisor, registro_conselho
        ],
        outputs=[
            tipo_estagio, razao_social, cnpj, nome_fantasia, endereco, bairro, cep, complemento, cidade, uf,
            email, telefone, representante, cpf_repr, nome_estudante, nascimento, cpf_estudante, rg, 
            endereco_estudante, bairro_estudante, cep_estudante, complemento_estudante, cidade_estudante, uf_estudante,
            email_estudante, telefone_estudante, curso_estudante, ano_periodo, matricula,
            orientador, data_inicio, data_termino, total_dias, horas_diarias, horas_semana_estagio, total_horas_estagio,
            seguradora, apolice, modalidade_estagio, remunerado, valor_bolsa, valor_extenso, auxilio_transporte,
            especificacao_auxilio, contraprestacao, especificacao_contraprestacao, horas_diarias_plano, horas_semanais_plano,
            total_horas_plano, horario_atividades,
            *atividades,
            nome_supervisor, formacao_supervisor, cargo_supervisor, registro_conselho
        ]
    )



import os
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.queue().launch(server_name="0.0.0.0", server_port=port)
