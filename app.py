import gradio as gr
from datetime import datetime, timedelta, date
from num2words import num2words
import re, time, httpx, unicodedata
from textwrap import dedent
from decimal import Decimal, InvalidOperation
# gradio==5.34.2
# num2words==0.5.14

from email_validator import validate_email, EmailNotValidError
import dns.resolver

import os
from dotenv import load_dotenv

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.message import EmailMessage


# Carregar variáveis do .env
load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_TLS  = os.getenv("SMTP_TLS", "true").lower() == "true"
FROM_EMAIL = os.getenv("FROM_EMAIL")


def enviar_email(destinatario: str, assunto: str, corpo: str, reply_to: str | None = None) -> bool:
    """
    Envia um e-mail texto (sem anexos). Retorna True se enviado com sucesso, False caso contrário.
    - destinatario: string com o e-mail de destino
    - assunto: assunto do e-mail
    - corpo: corpo do e-mail (texto simples)
    - reply_to: opcional, endereço para respostas (se None, usará FROM_EMAIL)
    """
    try:
        # Monta mensagem (texto simples)
        # Acrescenta aviso padrão de e-mail automático ao final do corpo
        aviso_auto = "\n\n---\nEste é um e-mail automático. Favor não respondê-lo."
        texto = f"{corpo.strip()}\n{aviso_auto}"

        msg = EmailMessage()
        msg.set_content(texto)
        msg["Subject"] = assunto
        # Recomendo usar um endereço "no-reply" ou o FROM_EMAIL configurado
        msg["From"] = FROM_EMAIL
        msg["To"] = destinatario

        # Define Reply-To (evita que respostas vão para o remetente real)
        reply_addr = reply_to or FROM_EMAIL
        msg["Reply-To"] = reply_addr

        # Cabeçalhos que sinalizam mensagem automática / bulk
        msg["Auto-Submitted"] = "auto-generated"   # indica que mensagem foi gerada automaticamente
        msg["Precedence"] = "bulk"                 # frequentemente usado para reduzir respostas automáticas
        # opcional: List-Unsubscribe
        # msg["List-Unsubscribe"] = "<mailto:unsubscribe@seu-dominio.com>"

        # Envio via SMTP
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            if SMTP_TLS:
                server.starttls()
            # login pode falhar se credenciais inválidas
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        # sucesso
        return True

    except Exception as e:
        # log no console (útil para diagnosticar no Render)
        print("❌ Erro ao enviar e-mail:", e)
        return False
        

UF_OPCOES = [
    "AC","AL","AM","AP","BA","CE","DF","ES","GO","MA",
    "MG","MS","MT","PA","PB","PE","PI","PR","RJ","RN",
    "RO","RR","RS","SC","SE","SP","TO"
]
UF_OPCOES_SET = set(UF_OPCOES)  # membership rápido

from datetime import date

def _parse_iso_date(s: str):
    try:
        return date.fromisoformat((s or "").strip())
    except Exception:
        return None

def validar_nascimento_estudante(valor: str):
    raw = (valor or "").strip()
    if not raw:
        return gr.update(value="", elem_classes=[])
    d = _parse_iso_date(raw)
    if not d:
        gr.Warning("⚠️ Data inválida.")
        return gr.update(value=raw, elem_classes=["erro"])
    if d > date.today():
        gr.Warning("⚠️ A data de nascimento não pode ser futura.")
        return gr.update(value=raw, elem_classes=["erro"])
    return gr.update(value=raw, elem_classes=[])


def validar_nascimento_representante(valor: str):
    raw = (valor or "").strip()
    if not raw:
        return gr.update(value="", elem_classes=[])
    d = _parse_iso_date(raw)
    if not d:
        gr.Warning("⚠️ Data inválida.")
        return gr.update(value=raw, elem_classes=["erro"])
    hoje = date.today()
    if d > hoje:
        gr.Warning("⚠️ A data de nascimento não pode ser futura.")
        return gr.update(value=raw, elem_classes=["erro"])
    try:
        limite_18 = hoje.replace(year=hoje.year - 18)
    except ValueError:
        limite_18 = hoje.replace(month=2, day=28, year=hoje.year - 18)
    if d > limite_18:
        gr.Warning("⚠️ O Representante deve ter pelo menos 18 anos.")
        return gr.update(value=raw, elem_classes=["erro"])
    return gr.update(value=raw, elem_classes=[])


VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
CEP_TIMEOUT = 4.0    # segundos
CEP_TTL = 3600       # 1h de cache simples em memória
__cep_cache = {}     # cep8 -> (ts, data|None)

def _only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def _cep8(raw: str) -> str:
    return _only_digits(raw)[:8]

def _cep_fmt(d: str) -> str:
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else d

def _cache_get(cep8): 
    hit = __cep_cache.get(cep8)
    if not hit: return None
    ts, data = hit
    if time.time() - ts > CEP_TTL:
        __cep_cache.pop(cep8, None)
        return None
    return data

def _cache_set(cep8, data):
    __cep_cache[cep8] = (time.time(), data)

def viacep_lookup(cep8: str):
    c = _cache_get(cep8)
    if c is not None:
        return c
    with httpx.Client(timeout=CEP_TIMEOUT) as client:
        r = client.get(VIACEP_URL.format(cep=cep8))
        r.raise_for_status()
        data = r.json()
        if data.get("erro"):
            _cache_set(cep8, None)
            return None
        _cache_set(cep8, data)
        return data

def validar_cep(valor: str):
    """
    Valida CEP brasileiro localmente (sem API).
    - Aceita entrada com/sem hífen e outros separadores.
    - Exige 8 dígitos numéricos.
    - Rejeita 00000-000.
    - Devolve formatado como 00000-000.
    - Integra com CSS .erro (já existente no app).
    """
    if not valor:  # campo vazio: não marca erro aqui (obrigatoriedade é na submissão)
        return gr.update(value="", elem_classes=[])

    # Mantém só dígitos
    cep = re.sub(r"\D", "", str(valor))

    # 8 dígitos?
    if len(cep) != 8:
        gr.Warning("⚠️ CEP inválido. Use o formato 00000-000.")
        return gr.update(value="", elem_classes=["erro"])

    # Evita CEP nulo
    if cep == "00000000":
        gr.Warning("⚠️ CEP inválido.")
        return gr.update(value="", elem_classes=["erro"])

    # Formata
    cep_fmt = f"{cep[:5]}-{cep[5:]}"
    return gr.update(value=cep_fmt, elem_classes=[])

def validar_cep_com_api(cep_val, end_val, bairro_val, cidade_val, uf_val):
    # 1) validação local (sua função atual)
    upd_local = validar_cep(cep_val)  # gr.update(...)
    cep_fmt = upd_local.get("value") or ""
    cep_ok = bool(cep_fmt) and (upd_local.get("elem_classes") in ([], None))

    # base: refletir resultado local
    out = [
        upd_local,
        gr.update(value=end_val or ""),     # endereço
        gr.update(value=bairro_val or ""),  # bairro
        gr.update(value=cidade_val or ""),  # cidade
        gr.update(value=uf_val or None),    # uf (dropdown)
    ]
    if not cep_ok:
        return tuple(out)

    # 2) CEP local ok → consulta ViaCEP
    d = re.sub(r"\D", "", cep_fmt)[:8]
    try:
        info = viacep_lookup(d)
    except Exception:
        gr.Warning("⚠️ Falha ao consultar o ViaCEP agora. Tente novamente.")
        return tuple(out)

    if not info:
        gr.Warning("⚠️ CEP não encontrado na base ViaCEP.")
        out[0] = gr.update(value=cep_fmt, elem_classes=["erro"])
        return tuple(out)

    # 3) sucesso: extrair campos
    end_api    = (info.get("logradouro")  or "").strip()
    bairro_api = (info.get("bairro")      or "").strip()
    cidade_api = (info.get("localidade")  or "").strip()
    uf_api     = (info.get("uf")          or "").strip().upper() or None

    # helper: manter o que o usuário pôs; senão, preencher com API
    def keep_or_fill(cur, api):
        return cur if (cur or "").strip() else (api or "")

    # 4) aplicar política
    # CEP: ok
    out[0] = gr.update(value=cep_fmt, elem_classes=[])

    # Endereço/Bairro: só preenche se estiverem vazios; não inventa quando API vier vazia
    novo_end    = keep_or_fill(end_val,    end_api)
    novo_bairro = keep_or_fill(bairro_val, bairro_api)
    out[1] = gr.update(value=novo_end,    elem_classes=[])
    out[2] = gr.update(value=novo_bairro, elem_classes=[])

    # Cidade/UF: SEMPRE sobrescrever pelos dados da API (mais confiáveis)
    out[3] = gr.update(value=cidade_api, elem_classes=[])

    # UF: garantir que existe nas opções do dropdown
    if uf_api in UF_OPCOES:
        out[4] = gr.update(value=uf_api, elem_classes=[])
    else:
        # se a API não trouxe UF válida, não force valor (mantém como está)
        out[4] = gr.update(value=(uf_val or None), elem_classes=[])

    # 5) CEP genérico de município (logradouro/bairro vazios): orientar usuário
    if not novo_end or not novo_bairro:
        gr.Info("ℹ️ CEP genérico do município: preencha manualmente Endereço e Bairro.")

    return tuple(out)

AUTO_CORRIGIR_CIDADE_UF = True  # defina False se quiser apenas marcar erro e interromper

def _norm(x: str) -> str:
    x = (x or "").strip().lower()
    x = unicodedata.normalize("NFD", x)
    x = "".join(ch for ch in x if unicodedata.category(ch) != "Mn")
    x = re.sub(r"\s+", " ", x)
    return x

def validar_cidade_uf_por_cep(dados: dict, updates: dict, nomes_completos: list, prefixo: str, UF_OPCOES=None):
    """Valida se cidade/UF batem com ViaCEP para o CEP. prefixo "" ou 'estudante'."""
    def nome(c): return f"{c}_{prefixo}" if prefixo else c
    def idx(n): return nomes_completos.index(n)

    n_cep, n_cidade, n_uf = nome("cep"), nome("cidade"), nome("uf")

    cep_raw = (dados.get(n_cep) or "").strip()
    cep8 = re.sub(r"\D", "", cep_raw)[:8]
    if len(cep8) != 8 or cep8 == "00000000":
        updates[idx(n_cep)] = gr.update(elem_classes=["erro"])
        gr.Warning(f"⚠️ CEP inválido em '{n_cep}'.")
        return False

    try:
        info = viacep_lookup(cep8)
    except Exception:
        updates[idx(n_cep)] = gr.update(elem_classes=["erro"])
        gr.Warning(f"⚠️ Não foi possível validar {n_cep} agora. Tente novamente.")
        return False

    if not info:
        updates[idx(n_cep)] = gr.update(elem_classes=["erro"])
        gr.Warning(f"⚠️ {n_cep} não encontrado (ViaCEP).")
        return False

    cidade_api = (info.get("localidade") or "").strip()
    uf_api     = (info.get("uf") or "").strip().upper()

    cidade_user = (dados.get(n_cidade) or "").strip()
    uf_user     = (dados.get(n_uf) or "").strip().upper()

    ok_cidade = _norm(cidade_user) == _norm(cidade_api) if cidade_api else True
    ok_uf     = (uf_user == uf_api) if uf_api else True

    # padroniza CEP
    updates[idx(n_cep)] = gr.update(value=f"{cep8[:5]}-{cep8[5:]}", elem_classes=[])

    if ok_cidade and ok_uf:
        return True

    # Divergência → corrigir ou marcar erro
    msgs = []
    if not ok_cidade:
        msgs.append(f"cidade = '{cidade_api}'")
        updates[idx(n_cidade)] = (
            gr.update(value=cidade_api, elem_classes=[]) if AUTO_CORRIGIR_CIDADE_UF
            else gr.update(elem_classes=["erro"])
        )
    if not ok_uf:
        msgs.append(f"UF = '{uf_api}'")
        if UF_OPCOES is None or (uf_api in UF_OPCOES_SET):
            updates[idx(n_uf)] = (
                gr.update(value=uf_api, elem_classes=[]) if AUTO_CORRIGIR_CIDADE_UF
                else gr.update(elem_classes=["erro"])
            )
        else:
            updates[idx(n_uf)] = gr.update(elem_classes=["erro"])


    gr.Warning("⚠️ Cidade/UF não conferem com o CEP. Valor esperado: " + ", ".join(msgs) + ".")
    return AUTO_CORRIGIR_CIDADE_UF

AUTO_CORRIGIR_CIDADE_UF_NO_BLUR = False  # mantemos só sinalização, sem autocorrigir

def validar_cidade_uf_blur(cep_val, cidade_val, uf_val):
    """
    Valida no blur de CIDADE ou UF:
    - Compara (cidade/uf) informados com ViaCEP do CEP.
    - Se só a cidade divergir -> limpa/erro APENAS a cidade.
    - Se só a UF divergir     -> limpa/erro APENAS a UF.
    - Se ambos divergirem     -> limpa/erro ambos.
    - Se baterem               -> remove erros.
    - Se CEP inválido/sem API  -> não altera nada.
    Retorna: (update_cidade, update_uf)
    """
    # 0) precisa de CEP válido
    cep8 = re.sub(r"\D", "", (cep_val or ""))[:8]
    if len(cep8) != 8 or cep8 == "00000000":
        return (
            gr.update(value=(cidade_val or ""), elem_classes=[]),
            gr.update(value=(uf_val or None),  elem_classes=[]),
        )

    # 1) ViaCEP
    try:
        info = viacep_lookup(cep8)
    except Exception:
        gr.Warning("⚠️ Não foi possível validar cidade/UF agora (rede).")
        return (
            gr.update(value=(cidade_val or ""), elem_classes=[]),
            gr.update(value=(uf_val or None),  elem_classes=[]),
        )
    if not info:
        gr.Warning("⚠️ CEP não encontrado na base ViaCEP; não é possível validar cidade/UF.")
        return (
            gr.update(value=(cidade_val or ""), elem_classes=[]),
            gr.update(value=(uf_val or None),  elem_classes=[]),
        )

    # 2) compara
    cidade_api = (info.get("localidade") or "").strip()
    uf_api     = (info.get("uf") or "").strip().upper()

    def _norm(x: str) -> str:
        import unicodedata, re as _re
        x = (x or "").strip().lower()
        x = unicodedata.normalize("NFD", x)
        return _re.sub(r"\s+", " ", "".join(ch for ch in x if unicodedata.category(ch) != "Mn"))

    uf_user   = (str(uf_val or "")).upper()
    ok_cidade = _norm(cidade_val) == _norm(cidade_api) if cidade_api else True
    ok_uf     = (uf_user == uf_api) if uf_api else True

    # 3) construir updates por campo, limpando somente o que divergiu
    updates_cidade = gr.update(value=(cidade_val or ""), elem_classes=[])
    updates_uf     = gr.update(value=(uf_val or None),  elem_classes=[])

    msgs = []
    if not ok_cidade:
        updates_cidade = gr.update(value="", elem_classes=["erro"])   # limpa SÓ cidade
        msgs.append(f"cidade = '{cidade_api}'")
    if not ok_uf:
        updates_uf = gr.update(value=None, elem_classes=["erro"])     # limpa SÓ UF (dropdown)
        msgs.append(f"UF = '{uf_api}'")

    if msgs:
        gr.Warning("⚠️ Cidade/UF não conferem com o CEP. Esperado: " + ", ".join(msgs) + ".")
        return (updates_cidade, updates_uf)

    # 4) tudo ok → remover erros e manter valores
    return (
        gr.update(value=(cidade_val or ""), elem_classes=[]),
        gr.update(value=(uf_val or None),  elem_classes=[]),
    )


# def rg_normalizar(raw: str) -> str: # OK
#     # remove tudo que não for dígito ou X/x
#     import re
#     v = re.sub(r"[^0-9Xx]", "", raw or "").upper()
#     if "X" in v[:-1]:  # X só pode ser no final
#         return v  # inválido, deixo a validação tratar
#     return v

# def rg_valido(br_rg: str) -> bool: # OK
#     v = rg_normalizar(br_rg)
#     if not v:
#         return False
#     if "X" in v[:-1]:
#         return False
#     corpo = v[:-1] if v[-1] == "X" else v
#     if not corpo.isdigit():
#         return False
#     return 7 <= len(v) <= 10

# def rg_formatar(br_rg: str) -> str: # OK
#     v = rg_normalizar(br_rg)
#     if not v:
#         return ""
#     dv = v[-1] if v[-1] == "X" else v[-1]
#     corpo = v[:-1] if v[-1] in "X0123456789" else v
#     if corpo.isdigit():
#         if len(v) == 9:   # 8+DV
#             return f"{corpo[:2]}.{corpo[2:5]}.{corpo[5:8]}-{dv}"
#         if len(v) == 8:   # 7+DV
#             return f"{corpo[:1]}.{corpo[1:4]}.{corpo[4:7]}-{dv}"
#     return v  # fallback sem máscara


# PRESERVAR_PONTUACAO_RG = True  # mantém exatamente como o usuário digitou quando RG for válido

# def rg_normaliza(raw: str) -> str:
#     """
#     Mantém apenas dígitos e, se houver, UM 'X' final (maiúsculo).
#     Ex.: '12.345.678-9' -> '123456789', '12.345.678-x' -> '12345678X'
#     """
#     s = (raw or "").strip().upper()
#     s = re.sub(r"[^0-9X]", "", s)
#     if "X" in s[:-1]:   # 'X' só pode no fim
#         s = s.replace("X", "")
#     return s

PRESERVAR_PONTUACAO_RG = True  # mantém como digitado quando RG for válido

def rg_eh_rg_simples(raw: str) -> bool:
    """
    RG simples (7–10), aceita só dígitos e 'X' APENAS no final (e no máximo 1).
    Bloqueia todos zeros/todos iguais.
    """
    s = (raw or "").strip().upper()

    # 🔴 Rejeita já aqui: 'X' fora do final ou mais de um 'X'
    if 'X' in s and (s.count('X') > 1 or not s.endswith('X')):
        return False

    # mantém apenas dígitos e, se houver, um 'X' final
    n = re.sub(r"[^0-9X]", "", s)

    # faixa da sua versão original
    if not (7 <= len(n) <= 10):
        return False

    # separa corpo/dv
    if n.endswith('X'):
        corpo = n[:-1]
        if not corpo.isdigit():
            return False
    else:
        if not n.isdigit():
            return False
        corpo = n

    # bloqueios
    if set(corpo) == {'0'} or len(set(corpo)) == 1:
        return False

    return True

def rg_formatar(raw: str) -> str:
    """Formata RG: pontos a cada 3 + hífen antes do último caractere."""
    s = (raw or "").strip().upper()
    # não mexa na regra do X aqui; só formata o que vier
    n = re.sub(r"[^0-9X]", "", s)
    if not n:
        return ""
    corpo, dv = n[:-1], n[-1]
    grupos, rest = [], corpo
    while rest:
        grupos.append(rest[:3]); rest = rest[3:]
    base = ".".join(grupos) if grupos else ""
    return f"{base}-{dv}" if base else n

def validar_rg_front(valor: str):
    raw = (valor or "").strip()
    if not raw:
        return gr.update(value="", elem_classes=[])
    if rg_eh_rg_simples(raw):
        return gr.update(
            value=(raw if PRESERVAR_PONTUACAO_RG else rg_formatar(raw)),
            elem_classes=[]
        )
    gr.Warning("⚠️ RG inválido. Use 7–10 dígitos (opcional 'X' só no final). Ex.: 12.345.678-9")
    return gr.update(value="", elem_classes=["erro"])


def _so_digitos(s: str) -> str:
    return re.sub(r"\D", "", s or "")

# DDDs válidos (ANATEL): 11-19, 21-24, 27-28, 31-35, 37-38, 41-49, 51-55,
# 61-69, 71-75, 77, 79, 81-89, 91-99
DDD_VALIDOS = {
    *[str(x) for x in range(11,20)],
    *[str(x) for x in range(21,25)], 27, 28,
    *[str(x) for x in range(31,36)], 37, 38,
    *[str(x) for x in range(41,50)],
    *[str(x) for x in range(51,56)],
    *[str(x) for x in range(61,70)],
    *[str(x) for x in range(71,76)], 77, 79,
    *[str(x) for x in range(81,90)],
    *[str(x) for x in range(91,100)],
}
DDD_VALIDOS = {str(x) for x in DDD_VALIDOS}  # garante strings

def _todos_iguais(s: str) -> bool:
    return s and all(ch == s[0] for ch in s)

def telefone_valido_br(dig: str) -> bool:
    """
    Regras (Brasil):
    - Aceita DDD + número: 10 dígitos (fixo) ou 11 dígitos (celular).
    - Permite prefixo +55 (12 ou 13 dígitos; removemos antes de validar).
    - DDD deve ser válido (ANATEL).
    - Fixo: primeiro dígito do número (após DDD) ∈ {2,3,4,5}.
    - Celular: primeiro dígito do número (após DDD) = 9.
    - Rejeita sequências inválidas (número local todo zero ou todos dígitos iguais).
    """
    d = _so_digitos(dig)

    # remove +55 se vier junto e o comprimento for compatível
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]

    # precisa ser 10 (fixo) ou 11 (celular)
    if len(d) not in (10, 11):
        return False

    ddd = d[:2]
    numero = d[2:]

    # DDD válido
    if ddd not in DDD_VALIDOS:
        return False

    # bloquear número local obviamente inválido
    if set(numero) == {"0"} or _todos_iguais(numero):
        return False

    # regras de prefixo
    if len(d) == 10:
        # fixo começa em 2-5
        return numero[0] in {"2", "3", "4", "5"}
    else:
        # celular começa em 9
        return numero[0] == "9"

def formatar_telefone_br(dig: str) -> str:
    d = _so_digitos(dig)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) == 10:  # fixo
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    if len(d) == 11:  # celular
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    return dig  # fallback

def validar_telefone(valor: str):
    """
    Para blur/change nos inputs.
    - Se válido → normaliza e formata.
    - Se inválido → limpa o campo e aplica .erro.
    """
    raw = (valor or "").strip()
    if not raw:
        return gr.update(value="", elem_classes=[])
    if telefone_valido_br(raw):
        return gr.update(value=formatar_telefone_br(raw), elem_classes=[])
    gr.Warning("⚠️ Telefone inválido. Ex.: fixo (62) 2345-6789 ou celular (62) 91234-5678.")
    return gr.update(value="", elem_classes=["erro"])

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
    if dv1 != int(d[9]): 
        return False
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
    raw = (valor or "").strip()

    # se o campo foi deixado em branco, não marca erro (você valida obrigatoriedade no submit)
    if not raw:
        return gr.update(value="", elem_classes=[])

    d = _apenas_digitos(raw)

    # precisa ter 11 dígitos numéricos
    if len(d) != 11:
        gr.Warning("⚠️ CPF inválido. Informe 11 dígitos no formato 000.000.000-00.")
        return gr.update(value="", elem_classes=["erro"])

    # dígitos ok, checa DV
    if not _valida_cpf(d):
        gr.Warning("⚠️ CPF inválido. Verifique os dígitos verificadores.")
        return gr.update(value="", elem_classes=["erro"])

    # válido → formata e remove erro
    return gr.update(value=_formata_cpf(d), elem_classes=[])

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

def calcular_total_dias(data_inicio, data_termino, contar_finais_semana, qtd_feriados):
    if not data_inicio or not data_termino:
        return gr.update(value="")

    try:
        dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_termino = datetime.strptime(data_termino, "%Y-%m-%d")
        if dt_termino < dt_inicio:
            gr.Warning("⚠️ A data de término não pode ser anterior à data de início.")
            return gr.update(value="")
    except ValueError:
        return gr.update(value="")

    # feriados (inteiro ≥ 0)
    try:
        feriados = int(qtd_feriados or 0)
        if feriados < 0:
            feriados = 0
    except Exception:
        feriados = 0

    # === LÓGICA AJUSTADA ===
    # "Sim"  -> NÃO contar finais de semana (excluir sábados e domingos)
    # "Não"  -> CONTAR finais de semana (incluir sábados e domingos)
    conta = {0, 1, 2, 3, 4}  # seg a sex
    if contar_finais_semana == "Não":
        conta.update({5, 6})  # inclui sábados e domingos

    # conta dias [início, término] inclusivo
    dias = 0
    atual = dt_inicio
    while atual <= dt_termino:
        if atual.weekday() in conta:
            dias += 1
        atual += timedelta(days=1)

    dias_efetivos = max(0, dias - feriados)
    return gr.update(value=f"{dias_efetivos} dias")


def montar_corpo_email(dados: dict, atividades: list[str]) -> str:
    g = lambda k: (str(dados.get(k, "") or "").strip())

    def _fmt_horas(v: str) -> str:
        """
        Converte '4,0' -> '4h' ; '4,5' -> '4h30min' ; '0,5' -> '30min'
        Aceita vírgula ou ponto como separador decimal.
        """
        s = (v or "").strip()
        if not s:
            return ""
        try:
            # aceita "4,5" ou "4.5"
            val = float(s.replace(",", "."))
            if val < 0:
                return s  # não formata valores negativos
            h = int(val)
            m = int(round((val - h) * 60))
            # trata arredondamento 59.999 -> 60
            if m == 60:
                h += 1
                m = 0
            if h > 0 and m > 0:
                return f"{h}h{m:02d}min"
            if h > 0 and m == 0:
                return f"{h}h"
            if h == 0 and m > 0:
                return f"{m}min"
            return "0h"
        except ValueError:
            return s

    def _fmt_brl(v: str) -> str:
        """
        Converte '759' -> 'R$ 759,00' ; '1234,5' -> 'R$ 1.234,50'
        Aceita vírgula ou ponto como separador decimal; ignora separador de milhar comum.
        """
        s = (v or "").strip()
        if not s:
            return ""
        # normaliza: remove separadores de milhar e padroniza decimal com ponto
        # exemplos aceitos: '1.234,56' | '1234,56' | '1234.56' | '759'
        normalized = s.replace(".", "").replace(",", ".")
        try:
            quant = Decimal(normalized).quantize(Decimal("0.01"))
            # formata em padrão en_US e depois troca separadores para pt-BR
            en = f"{quant:,.2f}"           # '1,234.56'
            br = en.replace(",", "X").replace(".", ",").replace("X", ".")
            return f"R$ {br}"
        except (InvalidOperation, ValueError):
            # se não conseguir converter, retorna como veio (sem quebrar fluxo)
            return s

    atividades_linhas = [
        f"{i}. {str(a).strip()}"
        for i, a in enumerate(atividades, start=1)
        if str(a or "").strip()
    ]
    bloco_atividades = (
        "=== ATIVIDADES ===\n" + "\n".join(atividades_linhas) + "\n\n"
        if atividades_linhas else ""
    )

    corpo = f"""
    Prezado(a) Coordenador(a),

    Segue dados para o Termo de Compromisso de Estágio do(a) estudante {g('nome_estudante')} a ser formalizado no SUAP.
            
    === TERMO DE COMPROMISSO DE ESTÁGIO ===
    Tipo de Estágio: {g('tipo_estagio')}

    === DADOS DO(A) CONCEDENTE ===
    Razão Social: {g('razao_social')}
    CNPJ: {g('cnpj')}
    Nome Fantasia: {g('nome_fantasia')}
    Endereço: {g('endereco')}
    Bairro: {g('bairro')}
    CEP: {g('cep')}
    Complemento: {g('complemento')}
    Cidade: {g('cidade')}
    UF: {g('uf')}
    E-mail: {g('email')}
    Telefone: {g('telefone')}
    Representante: {g('representante')}
    Nascimento do Representante: {g('nascimento_repr')}
    CPF Representante: {g('cpf_repr')}

    === DADOS DO(A) ESTUDANTE ===
    Nome do(a) Estudante: {g('nome_estudante')}
    Nascimento: {g('nascimento')}
    CPF do(a) Estudante: {g('cpf_estudante')}
    RG do(a) Estudante: {g('rg')}
    Endereço do(a) Estudante: {g('endereco_estudante')}
    Bairro do(a) Estudante: {g('bairro_estudante')}
    CEP do(a) Estudante: {g('cep_estudante')}
    Complemento: {g('complemento_estudante')}
    Cidade do(a) Estudante: {g('cidade_estudante')}
    UF do(a) Estudante: {g('uf_estudante')}
    E-mail do(a) Estudante: {g('email_estudante')}
    Telefone do(a) Estudante: {g('telefone_estudante')}
    Curso do(a) Estudante: {g('curso_estudante')}
    Ano/Período Letivo: {g('ano_periodo')}
    Matrícula: {g('matricula')}
    Orientador(a): {g('orientador')}

    === CLÁUSULA SEGUNDA – DA DURAÇÃO ===
    Data de Início: {g('data_inicio')}
    Data de Término: {g('data_termino')}
    Total de Dias de Estágio: {g('total_dias')}

    === CLÁUSULA QUARTA – DA CARGA HORÁRIA ===
    Horas Diárias: {_fmt_horas(g('horas_diarias'))}
    Horas Semanais de Estágio: {g('horas_semana_estagio')}
    Total de Horas de Estágio: {g('total_horas_estagio')}

    === CLÁUSULA SEXTA – DO SEGURO ===
    Seguradora: {g('seguradora')}
    Apólice: {g('apolice')}

    === CLÁUSULA SÉTIMA – DOS BENEFÍCIOS ===
    Modalidade do Estágio: {g('modalidade_estagio')}
    Remunerado: {g('remunerado')}
    Valor da Bolsa: {_fmt_brl(g('valor_bolsa'))}
    Valor por Extenso: {g('valor_extenso')}
    Auxílio Transporte: {g('auxilio_transporte')}
    Especificação do Auxílio Transporte: {g('especificacao_auxilio')}
    Contraprestação de Serviços: {g('contraprestacao')}
    Especificação da Contraprestação: {g('especificacao_contraprestacao')}

    === CLÁUSULA NONA – PLANO DE ATIVIDADES DE ESTÁGIO ===
    Horas Diárias no Plano: {g('horas_diarias_plano')}
    Horas Semanais do Plano de Atividades: {g('horas_semanais_plano')}
    Total de Horas do Plano de Atividades: {g('total_horas_plano')}
    Horário das Atividades: {g('horario_atividades')}

    {bloco_atividades}
    === SUPERVISOR(A) DO ESTÁGIO ===
    Nome do(a) Supervisor(a): {g('nome_supervisor')}
    Formação do(a) Supervisor(a): {g('formacao_supervisor')}
    Cargo/Função do(a) Supervisor(a) no(a) concedente: {g('cargo_supervisor')}
    Registro no Conselho: {g('registro_conselho')}
    
    
    Atenciosamente,  
    {g('nome_estudante')}
    """
    return dedent(corpo).rstrip()


# === Função principal ===
def processar_formulario(*args):
    # ------------------------------
    # 1) Campos FIXOS (até "horario_atividades")
    #    -> Deixe essa lista exatamente nessa ordem,
    #       pois é a ordem em que você coloca os inputs antes do *atividades
    nomes_fixos = [
        "tipo_estagio", "razao_social", "cnpj", "nome_fantasia", "endereco", "bairro",
        "cep", "complemento", "cidade", "uf", "email", "telefone",
        "representante", 
        "nascimento_repr",
        "cpf_repr", 
        "nome_estudante", 
        "nascimento", "cpf_estudante", "rg",
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
        "nascimento_repr": "Data de Nascimento do Representante",
        "cpf_repr": "CPF do Representante Legal",
        "nome_estudante": "Nome do(a) Estudante",
        "nascimento": "Data de Nascimento do Estudante",
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
    
    # ... (depois de montar dados/updates/nomes_completos)

    # valida coerência cidade/UF com CEP — concedente
    ok_concedente = validar_cidade_uf_por_cep(
        dados, updates, nomes_completos, prefixo="", UF_OPCOES=UF_OPCOES_SET
    )
    if not ok_concedente:
        return updates

    # valida coerência cidade/UF com CEP — estudante
    ok_estudante = validar_cidade_uf_por_cep(
        dados, updates, nomes_completos, prefixo="estudante", UF_OPCOES=UF_OPCOES_SET
    )
    if not ok_estudante:
        return updates
    
    # =========================
    # 1) Validação das Datas de Nascimento
    # =========================
    ANO_MIN = 1900
    
    def _parse_iso_date_local(s: str):
        try:
            return date.fromisoformat((s or "").strip())
        except Exception:
            return None
    
    def _ano_ok(d: date) -> bool:
        return ANO_MIN <= d.year <= date.today().year


    # 1) Validações específicas
    campos_com_erro = set()

    def falha_especifica(nome, idx, msg):
        updates[idx] = gr.update(elem_classes=["erro"])
        gr.Warning(msg)
        campos_com_erro.add(nome)

    # idx e valores crus
    idx_nasc      = nomes_completos.index("nascimento")
    idx_nasc_repr = nomes_completos.index("nascimento_repr")

    nasc_raw      = (dados.get("nascimento") or "").strip()
    nasc_repr_raw = (dados.get("nascimento_repr") or "").strip()
    
#     print("DBG nasc_raw =", repr(nasc_raw))
#     print("DBG nasc_repr_raw =", repr(nasc_repr_raw))

    hoje = date.today()
    # trata 29/02 em anos não bissextos
    try:
        limite_18 = hoje.replace(year=hoje.year - 18)
    except ValueError:
        limite_18 = hoje.replace(month=2, day=28, year=hoje.year - 18)

    # Estudante — se veio preenchido: inválida/futura
    if nasc_raw:
        d = _parse_iso_date_local(nasc_raw)
        if not d or not _ano_ok(d):
            falha_especifica("nascimento", idx_nasc, f"⚠️ Data de nascimento inválida (ano deve ser ≥ {ANO_MIN}).")
        elif d > hoje:
            falha_especifica("nascimento", idx_nasc, "⚠️ A data de nascimento do(a) estudante não pode ser futura.")


    # Representante — se veio preenchido: inválida/futura/<18
    if nasc_repr_raw:
        d = _parse_iso_date_local(nasc_repr_raw)
        if not d or not _ano_ok(d):
            falha_especifica("nascimento_repr", idx_nasc_repr,\
                             f"⚠️ Data de nascimento do(a) representante inválida (ano deve ser ≥ {ANO_MIN}).")
        elif d > hoje:
            falha_especifica("nascimento_repr", idx_nasc_repr,\
                             "⚠️ A data de nascimento do(a) representante não pode ser futura.")
        elif d > limite_18:
            falha_especifica("nascimento_repr", idx_nasc_repr, "⚠️ O(A) representante deve ter pelo menos 18 anos.")

    data_inicio  = dados["data_inicio"]
    data_termino = dados["data_termino"]
    nascimento   = dados["nascimento"]
    nascimento_repr = dados["nascimento_repr"]

    # datas obrigatórias de período
    try:
        dt_inicio  = datetime.strptime(data_inicio,  "%Y-%m-%d")
        dt_termino = datetime.strptime(data_termino, "%Y-%m-%d")
    except ValueError:
        gr.Warning("⚠️ Formato inválido de data (início/término). Use o seletor de calendário.")
        return updates

    # nascimento do estudante (opcional aqui, erros específicos já foram avisados acima)
    dt_nascimento = None
    if nascimento:
        try:
            dt_nascimento = datetime.strptime(nascimento, "%Y-%m-%d")
        except ValueError:
            # Se quiser, marque o campo como erro específico, em vez de mensagem genérica:
            falha_especifica("nascimento", idx_nasc, "⚠️ Data de nascimento inválida.")
            return updates

    # nascimento do representante (idem)
    dt_nascimento_repr = None
    if nascimento_repr:
        try:
            dt_nascimento_repr = datetime.strptime(nascimento_repr, "%Y-%m-%d")
        except ValueError:
            falha_especifica("nascimento_repr", idx_nasc_repr, "⚠️ Data de nascimento do(a) representante inválida.")
            return updates

    if dt_termino < dt_inicio:
        gr.Warning("⚠️ A data de término não pode ser anterior à data de início.")
        return updates

    dados['data_inicio']      = dt_inicio.strftime("%d/%m/%Y")
    dados['data_termino']     = dt_termino.strftime("%d/%m/%Y")
    if dt_nascimento:
        dados['nascimento']   = dt_nascimento.strftime("%d/%m/%Y")
    if dt_nascimento_repr:
        dados['nascimento_repr'] = dt_nascimento_repr.strftime("%d/%m/%Y")


    # (Se você precisa dos formatos dd/mm/aaaa depois, faça a conversão aqui em variáveis locais,
    #   mas NÃO altere args; o 'updates' é só para UI)

    # =========================
    # 4) Atividades (mínimo 5) com borda vermelha
    # =========================
    indices_atividades = [
        nomes_completos.index(f"atividade_{i}")
        for i in range(1, n_atividades + 1)
    ]
    # valores normalizados
    valores_atividades = [
        (i, (str(args[i]).strip() if args[i] is not None else ""))
        for i in indices_atividades
    ]

    preenchidas = [(i, v) for (i, v) in valores_atividades if v]
    vazias = [i for (i, v) in valores_atividades if not v]

   # 1) zere as classes de TODAS as atividades visíveis (remove vermelho antigo)
    for idx in indices_atividades:
        updates[idx] = gr.update(value=args[idx], elem_classes=[])

    # 2) regra do mínimo
    MIN_REQ = 5
    if len(preenchidas) < MIN_REQ:
        faltam = MIN_REQ - len(preenchidas)

        # marque de vermelho apenas as primeiras 'faltam' vazias
        for idx in vazias[:faltam]:
            updates[idx] = gr.update(value=args[idx], elem_classes=["erro"])

        gr.Warning(f"⚠️ Informe pelo menos {MIN_REQ} atividades (faltam {faltam}).")
        return updates
    
    # =========================
    # Obrigatórios gerais
    # =========================
    erros_rotulos = []
    for idx, nome in enumerate(nomes_completos[:len(args)]):
        if nome in campos_com_erro:
            # já marcamos erro específico e mostramos mensagem
            continue

        obrigatorio = nome in campos_obrigatorios
        valor = args[idx]
        vazio = (valor is None) or (str(valor).strip().lower() in ["", "none"])

        if obrigatorio and vazio:
            marcar_erro(nome, True)  # preencha updates[idx] internamente, como você já faz
            erros_rotulos.append(campos_obrigatorios[nome])
        else:
            marcar_erro(nome, False)

    if campos_com_erro or erros_rotulos:
        if erros_rotulos:
            lista = ", ".join(erros_rotulos[:4]) + ("..." if len(erros_rotulos) > 4 else "")
            gr.Warning(f"⚠️ Preencha os campos obrigatórios destacados em vermelho: {lista}.")
        # ATENÇÃO: se sua função espera lista de updates na ordem,
        # converta aqui (ex.: with_indices -> list). Se você já usa dict->list em outro ponto, chame o mesmo helper.
        return updates  # ou: return out_list


    # ------------------------------
    # Se chegou aqui, está tudo OK — siga com o resto do processamento
    # (geração de PDF, prints, etc.)

    print("=== TERMO DE COMPROMISSO DE ESTÁGIO ===")
    print(f"Tipo de Estágio: {dados['tipo_estagio']}")
    print()
    print("=== DADOS DO(A) CONCEDENTE ===")
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
    print(f"Data de Nascimento do Representante: {dados['nascimento_repr']}")
    print(f"CPF Representante: {dados['cpf_repr']}")
    print()
    print("=== DADOS DO(A) ESTUDANTE ===")
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
    print()
    print("=== CLÁUSULA SEGUNDA – DA DURAÇÃO ===")
    print(f"Data de Início: {dados['data_inicio']}")
    print(f"Data de Término: {dados['data_termino']}")
    print(f"Total de Dias de Estágio: {dados['total_dias']}")
    print()
    print("=== CLÁUSULA QUARTA – DA CARGA HORÁRIA ===")
    print(f"Horas Diárias: {dados['horas_diarias']}")
    print(f"Horas Semanais de Estágio: {dados['horas_semana_estagio']}")
    print(f"Total de Horas de Estágio: {dados['total_horas_estagio']}")
    print()
    print("=== CLÁUSULA SEXTA – DO SEGURO ===")
    print(f"Seguradora: {dados['seguradora']}")
    print(f"Apólice: {dados['apolice']}")
    print()
    print("=== CLÁUSULA SÉTIMA – DOS BENEFÍCIOS ===")
    print(f"Modalidade do Estágio: {dados['modalidade_estagio']}")
    print(f"Remunerado: {dados['remunerado']}")
    print(f"Valor da Bolsa: {dados['valor_bolsa']}")
    print(f"Valor por Extenso: {dados['valor_extenso']}")
    print(f"Auxílio Transporte: {dados['auxilio_transporte']}")
    print(f"Especificação do Auxílio Transporte: {dados['especificacao_auxilio']}")
    print(f"Contraprestação de Serviços: {dados['contraprestacao']}")
    print(f"Especificação da Contraprestação: {dados['especificacao_contraprestacao']}")
    print()
    print("=== CLÁUSULA NONA – PLANO DE ATIVIDADES DE ESTÁGIO ===")
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
    
    
    # === Envia o e-mail após gerar as informações ===
    
    # Define o destinatário (pelo curso, ou fallback)
#     mapa_destinatarios = {
#         "Bacharelado em Administração": "lpa.cbe@ifgoiano.edu.br",
#         "Bacharelado em Zootecnia": "coordbachzoo.cbe@ifgoiano.edu.br",
#         "Técnico em Agropecuária": "coortecagro.cbe@ifgoiano.edu.br",
#         "Técnico em Administração": "coordtecadm.cbe@ifgoiano.edu.br",
#         "Técnico em Informática": "coordtecinfo.cbe@ifgoiano.edu.br",
#     }
#     curso = (dados.get("curso_estudante") or "").strip()
#     email_destinatario = mapa_destinatarios.get(curso, "estagio.cbe@ifgoiano.edu.br")  # fallback de testes

    email_destinatario = "estagio.cbe@ifgoiano.edu.br"
    #email_destinatario = "robson.campelo@gmail.com"

    assunto = f"Termo de Compromisso de Estágio - {dados.get('nome_estudante','').strip()}"

    corpo_email = montar_corpo_email(dados, atividades)

    # Envia e trata visualmente sem interromper o retorno dos outputs
    try:
        ok = enviar_email(
            destinatario=email_destinatario,
            assunto=assunto,
            corpo=corpo_email,
            reply_to="no-reply@ifgoiano.edu.br"
        )
        if ok:
            gr.Info("✅ TCE registrado e encaminhado com sucesso ao setor responsável.")
        else:
            gr.Warning("⚠️ Não foi possível enviar o e-mail agora. Tente novamente mais tarde.")
    except Exception as e:
        print(f"[ERRO] envio de e-mail: {e}")
        gr.Warning("⚠️ Não foi possível enviar o e-mail agora. Tente novamente mais tarde.")

   
    RADIOS = {
        "contar_finais_semana",
        "horas_diarias",
        "horas_diarias_plano",
        "tipo_estagio",
        "modalidade_estagio",
        "remunerado",
        "auxilio_transporte",
        "contraprestacao",
        "possui_cin",
    }

    DROPDOWNS = {
        "uf",
        "uf_estudante",
    }

    NUMBERS = {
        "qtd_feriados",  # só terá efeito se estiver em nomes_completos
    }

    def _reset_update(nome: str):
        if nome in RADIOS:
            return gr.update(value=("Não" if nome == "possui_cin" else None), elem_classes=[])
        if nome in DROPDOWNS:
            return gr.update(value=None, elem_classes=[])
        if nome in NUMBERS:
            return gr.update(value=None, elem_classes=[])
        if nome in {"nascimento", "nascimento_repr"}:
            return gr.update(value="", elem_classes=[])
        return gr.update(value="", elem_classes=[])

    out = []
    for nome in nomes_completos:
        out.append(_reset_update(nome))

#     print("✅ Termo registrado com sucesso!")
#     gr.Info("✅ Termo registrado com sucesso!")

    return out



with gr.Blocks(theme="default") as demo:
    gr.HTML("""
    <script>
    (function () {
      try {
        // Diz explicitamente que a página está em pt-BR
        document.documentElement.setAttribute("lang", "pt-BR");
        // Sinaliza a tradutores que não queremos tradução automática
        document.documentElement.setAttribute("translate", "no");
        document.documentElement.classList.add("notranslate");

        // Dica para o Google Translate
        var m = document.createElement("meta");
        m.setAttribute("name", "google");
        m.setAttribute("content", "notranslate");
        document.head.appendChild(m);
      } catch (e) {}
    })();
    </script>
    <style>
      /* Evita que engines que respeitam a propriedade CSS traduzam o conteúdo */
      .notranslate, .notranslate * { translate: none; }
    </style>
    """)
    
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
    
     # CSS anti-erro (se já não tiver)
    gr.HTML("""
    <style>
    .erro select {              /* dropdown */
      border-color:#dc2626!important; box-shadow:0 0 0 1px #dc2626 inset!important;
    }
    </style>
    """)
    
    gr.HTML("""
    <script>
      try {
        history.scrollRestoration = 'manual';
        window.addEventListener('DOMContentLoaded', ()=>{ window.scrollTo(0,0); });
        setTimeout(()=>{ window.scrollTo(0,0); }, 0);
      } catch(e){}
    </script>
    """)

    gr.Markdown("<h2 style='text-align: center;'>TERMO DE COMPROMISSO DE ESTÁGIO - TCE</h2>")
    
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
    
    uf.blur(validar_uf, inputs=uf, outputs=uf)  # 1º: valida a sigla
    uf.blur(                                     # 2º: cruza com CEP/Cidade
        validar_cidade_uf_blur,
        inputs=[cep, cidade, uf],
        outputs=[cidade, uf]
    )
    cidade.blur(validar_cidade_uf_blur, inputs=[cep, cidade, uf], outputs=[cidade, uf])
    
    # Concedente
    #cep.blur(validar_cep, inputs=cep, outputs=cep)
    cep.blur(
        validar_cep_com_api,
        inputs=[cep, endereco, bairro, cidade, uf],
        outputs=[cep, endereco, bairro, cidade, uf]
    )
    
    with gr.Row():
        email = gr.Textbox(label="E-mail*", placeholder="exemplo@dominio.com")
        telefone = gr.Text(label="Telefone (00) 00000-0000*", placeholder="Ex: (64) 91234-5678")
    
    telefone.blur(validar_telefone, inputs=telefone, outputs=telefone)
    
    email.blur(validar_email_estrito, inputs=email, outputs=email)

    with gr.Row():
        representante = gr.Text(label="Representante legal*")
        
        # seletor de data VISUAL
        # Representante
        gr.HTML("""
        <label for="input-nascimento-repr">Data de Nascimento do Representante (use o seletor abaixo)*</label><br>
        <input type="date" id="input-nascimento-repr"
          oninput="
            (function(){
              const src = document.getElementById('input-nascimento-repr');
              const dst = document.querySelector('#nascimento_repr input, #nascimento_repr textarea');
              if (!src || !dst) return;
              let v = src.value; // browsers válidos emitem YYYY-MM-DD
              // fallback: se o navegador permitir digitação em DD/MM/AAAA, converte:
              if (!v) {
                const raw = src.value || '';
                const m = raw.match(/^(\\d{2})\\/(\\d{2})\\/(\\d{4})$/);
                if (m) v = `${m[3]}-${m[2]}-${m[1]}`;
              }
              // copie mesmo se vazio, para permitir validação no backend
              // if (!v) return;
              if (dst.value !== v) {
                dst.value = v;
                dst.dispatchEvent(new Event('input', { bubbles:true }));
              }
            })();
          "
          onchange="
            (function(){
              const src = document.getElementById('input-nascimento-repr');
              const dst = document.querySelector('#nascimento_repr input, #nascimento_repr textarea');
              if (!src || !dst) return;
              let v = src.value;
              if (!v) {
                const raw = src.value || '';
                const m = raw.match(/^(\\d{2})\\/(\\d{2})\\/(\\d{4})$/);
                if (m) v = `${m[3]}-${m[2]}-${m[1]}`;
              }
              if (!v) return;
              if (dst.value !== v) {
                dst.value = v;
                dst.dispatchEvent(new Event('input', { bubbles:true }));
              }
            })();
          "
        >
        """)

        nascimento_repr = gr.Textbox(elem_id="nascimento_repr", visible=False)

        cpf_repr = gr.Text(label="CPF (000.000.000-00)*", placeholder="Ex: 123.456.789-00")
                                     
    # Representante
    nascimento_repr.change(fn=validar_nascimento_representante, inputs=nascimento_repr, outputs=nascimento_repr)

    cpf_repr.blur(validar_cpf, inputs=cpf_repr, outputs=cpf_repr)
    
    gr.Markdown("Do outro lado o(a) estudante,")
    
    gr.Markdown("### DADOS DO(A) ESTUDANTE")

    nome_estudante = gr.Text(label="Nome*")
    
    with gr.Row():
        # Campo visual com seletor de data
        # Estudante
        gr.HTML("""
        <label for="input-nascimento">Data de Nascimento (use o seletor abaixo)*</label><br>
        <input type="date" id="input-nascimento"
          oninput="
            (function(){
              const src = document.getElementById('input-nascimento');
              const dst = document.querySelector('#nascimento input, #nascimento textarea');
              if (!src || !dst) return;
              let v = src.value; // navegadores normalmente emitem YYYY-MM-DD
              // fallback: se o usuário digitar DD/MM/AAAA, converte para ISO
              if (!v) {
                const raw = src.value || '';
                const m = raw.match(/^(\\d{2})\\/(\\d{2})\\/(\\d{4})$/);
                if (m) v = `${m[3]}-${m[2]}-${m[1]}`;
              }
              // copie mesmo se vazio, para permitir validação no backend
              // if (!v) return;
              if (dst.value !== v) {
                dst.value = v;
                dst.dispatchEvent(new Event('input', { bubbles:true }));
              }
            })();
          "
          onchange="
            (function(){
              const src = document.getElementById('input-nascimento');
              const dst = document.querySelector('#nascimento input, #nascimento textarea');
              if (!src || !dst) return;
              let v = src.value;
              if (!v) {
                const raw = src.value || '';
                const m = raw.match(/^(\\d{2})\\/(\\d{2})\\/(\\d{4})$/);
                if (m) v = `${m[3]}-${m[2]}-${m[1]}`;
              }
              if (!v) return;
              if (dst.value !== v) {
                dst.value = v;
                dst.dispatchEvent(new Event('input', { bubbles:true }));
              }
            })();
          "
        >
        """)

        nascimento = gr.Textbox(elem_id="nascimento", visible=False)

        cpf_estudante = gr.Textbox(
            label="CPF (000.000.000-00)*",
            placeholder="Ex: 123.456.789-00"
        )

        possui_cin = gr.Radio(
            label="Possui a nova Carteira de Identidade Nacional (CIN)?",
            choices=["Sim", "Não"],
            value="Não",           # aparece “Não” marcado inicialmente
            interactive=True
        )
        rg = gr.Text(label="RG ou CIN*", elem_id="rg_estudante")  # seu campo existente
        
    
    def validar_rg_ou_cin(valor: str, opcao_cin: str):
        if (opcao_cin or "").strip().lower() == "sim":
            return validar_cpf(valor)   # mesma UX do CPF
        return validar_rg_front(valor)  # RG simples

    # Estudante
    nascimento.change(fn=validar_nascimento_estudante, inputs=nascimento, outputs=nascimento)
    
    # Quando sair do RG → valida conforme a escolha do Radio
    rg.blur(
        validar_rg_ou_cin,
        inputs=[rg, possui_cin],
        outputs=rg
    )
    
    # Opcional, mas recomendado: ao trocar Sim/Não, revalidar o que já está no campo
    possui_cin.change(
        validar_rg_ou_cin,
        inputs=[rg, possui_cin],
        outputs=rg
    )

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
    uf_estudante.blur(
        validar_cidade_uf_blur,
        inputs=[cep_estudante, cidade_estudante, uf_estudante],
        outputs=[cidade_estudante, uf_estudante]
    )

    # Estudante
    #cep_estudante.blur(validar_cep, inputs=cep_estudante, outputs=cep_estudante)
    cep_estudante.blur(
        validar_cep_com_api,
        inputs=[cep_estudante, endereco_estudante, bairro_estudante, cidade_estudante, uf_estudante],
        outputs=[cep_estudante, endereco_estudante, bairro_estudante, cidade_estudante, uf_estudante]
    )
    
    cidade_estudante.blur(validar_cidade_uf_blur, inputs=[cep_estudante, cidade_estudante, uf_estudante],\
                          outputs=[cidade_estudante, uf_estudante])
    
    
    with gr.Row():
        email_estudante = gr.Textbox(label="E-mail do Estudante*", placeholder="exemplo@dominio.com")
        telefone_estudante = gr.Text(label="Telefone (00) 00000-0000)*", placeholder="Ex: (64) 91234-5678")
    
    telefone_estudante.blur(validar_telefone, inputs=telefone_estudante, outputs=telefone_estudante)
    
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
        
       
    with gr.Row():
        contar_finais_semana = gr.Radio(
            label="Descontar os finais de semana do período de estágio?*",
            choices=["Sim", "Não"],
            interactive=True,
            value="Não"  # começa marcado em "Não"
        )
        qtd_feriados = gr.Number(
            label="Quantos dias de feriados devem ser desconsiderados no período previsto para estágio?",
            value=0,
            precision=0,      # inteiro
            interactive=True,
            minimum=0
        )
        
    # Atualiza o total de dias automaticamente
    # sempre que qualquer uma das entradas mudar, recalcule
    data_inicio.change(
        fn=calcular_total_dias,
        inputs=[data_inicio, data_termino, contar_finais_semana, qtd_feriados],
        outputs=total_dias
    )
    data_termino.change(
        fn=calcular_total_dias,
        inputs=[data_inicio, data_termino, contar_finais_semana, qtd_feriados],
        outputs=total_dias
    )
    contar_finais_semana.change(
        fn=calcular_total_dias,
        inputs=[data_inicio, data_termino, contar_finais_semana, qtd_feriados],
        outputs=total_dias
    )
    qtd_feriados.change(
        fn=calcular_total_dias,
        inputs=[data_inicio, data_termino, contar_finais_semana, qtd_feriados],
        outputs=total_dias
    )
        
    gr.Markdown("""
        **Parágrafo único.** O Estagiário terá direito a recesso de 30 (trinta) dias, compatíveis com suas férias escolares, sempre que o estágio tenha duração igual ou superior a 1 (um) ano. Sendo proporcional o recesso, em casos de estágio inferior a 1 (um) ano.

        ### CLÁUSULA TERCEIRA – DO VÍNCULO
        O estágio, tanto obrigatório quanto o não obrigatório, não cria vínculo empregatício de qualquer natureza, desde que observados os termos do art. 3º da Lei nº 11.788/2008 e as disposições do presente Termo.

        ### CLÁUSULA QUARTA – DA CARGA HORÁRIA
        A carga horária do Estágio será cumprida conforme apresentado na tabela abaixo, em consonância ao art. 10 da Lei nº 11.788/2008:
        """)
    
    # gera escolhas de 1, 1,5, 2, 2,5, ... 8
    horas_choices = [str(h/2).replace('.', ',') for h in range(2, 17)]  # 2/2=1  ... 16/2=8
    
    with gr.Row():
        horas_diarias = gr.Radio(
            choices=horas_choices,
            label="Horas diárias (marque o valor correspondente)*",
            info="Selecione de 1 a 8 horas, em intervalos de 30 minutos",
            value=None,
            interactive=True,
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
            value=None,
            interactive=False  # ← agora é calculado automaticamente
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
        
    # Radio do plano (preenchido automaticamente, sem edição)
    horas_diarias_plano = gr.Radio(
        label="Horas diárias (plano)*",
        choices=horas_choices,   # mesmas opções
        type="value",
        value=None,
        interactive=False         # impede edição manual
    )

    # 3) Função de sincronização
    # Sincronização (espelha exatamente o que foi escolhido na Quarta)
    def sincronizar_horas_diarias(v):
        # se limpar, limpa o espelho também
        if not v:
            return gr.update(value=None)
        # garante que o espelho tenha a mesma string (ex.: "1,5")
        return gr.update(value=str(v))

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
    
   
    def _parse_horas_diarias(txt: str):
        """
        Converte "1,5" -> 1.5 ; "2" -> 2.0 ; retorna None se vazio/ inválido.
        """
        if not txt:
            return None
        s = str(txt).strip().replace(',', '.')
        try:
            v = float(s)
            return v if v > 0 else None
        except Exception:
            return None

    def _parse_total_dias_label(lbl: str):
        """
        Converte "22 dias" -> 22 ; "1 dia" -> 1 ; "" -> None
        Aceita números no início da string.
        """
        if not lbl:
            return None
        m = re.search(r'\d+', str(lbl))
        if not m:
            return None
        try:
            return int(m.group(0))
        except Exception:
            return None

    def calcular_total_horas(horas_diarias_val, total_dias_label):
        hd = _parse_horas_diarias(horas_diarias_val)
        td = _parse_total_dias_label(total_dias_label)

        if hd is None or td is None:
            # faltando dados -> limpa
            return gr.update(value=None)

        horas = hd * td  # pode ser .0 ou .5 (porque hd é meia em meia)
        # formatar: se inteiro, sem casas; se .5, usar vírgula
        if abs(horas - round(horas)) < 1e-9:
            txt = f"{int(round(horas))} horas"
        else:
            txt = f"{str(horas).replace('.', ',')} horas"

        return gr.update(value=txt)
    
    # quando horas_diarias mudar
    horas_diarias.change(
        fn=calcular_total_horas,
        inputs=[horas_diarias, total_dias],
        outputs=total_horas_estagio
    )

    # quando total_dias mudar (datas / finais de semana / feriados)
    total_dias.change(
        fn=calcular_total_horas,
        inputs=[horas_diarias, total_dias],
        outputs=total_horas_estagio
    )

    
    # ==== ATIVIDADES DINÂMICAS (mín. 5, sem máximo prático) ====

    MAX_ATIVIDADES = 30  # pode ajustar se quiser
    MIN_ATIVIDADES = 5

    gr.Markdown("**As seguintes atividades serão desenvolvidas (mínimo de 5 atividades):**")

    with gr.Row():
        btn_add = gr.Button("➕ Adicionar atividade")
        btn_rem = gr.Button("➖ Remover última")

    # Estado: quantas atividades estão visíveis agora
    ativ_count = gr.State(MIN_ATIVIDADES)
    
    def limpar_erro(valor):
        # sempre que o usuário alterar o campo, limpamos a classe 'erro'
        return gr.update(elem_classes=[])

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
    
    # após o for que cria os componentes:
    for comp in atividades:
        # comp.change(limpar_erro, inputs=comp, outputs=comp)
        # se preferir limpar no desfocar em vez de a cada mudança:
        comp.blur(limpar_erro, inputs=comp, outputs=comp)


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
    with gr.Row():
        botao = gr.Button(value="Enviar Termo", variant="primary", elem_id="btn-enviar-termo")
    
    botao.click(
        fn=processar_formulario, 
        inputs=[
            tipo_estagio, razao_social, cnpj, nome_fantasia, endereco, bairro, cep, complemento, cidade, uf, 
            email, telefone, representante, nascimento_repr, cpf_repr, nome_estudante, nascimento, cpf_estudante, rg, 
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
            email, telefone, representante, nascimento_repr, cpf_repr, nome_estudante, nascimento, cpf_estudante, rg, 
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
