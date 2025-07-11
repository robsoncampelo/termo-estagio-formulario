#!/usr/bin/env python
# coding: utf-8

# In[8]:


import gradio as gr
from datetime import datetime
from num2words import num2words
import re

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
    except:
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

    # Lista base de nomes de campos (sem atividades)
    nomes_completos = [
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
        "horario_atividades",
    ]

    # Acrescenta as atividades ANTES dos campos do supervisor
    for i in range(1, 11):
        nomes_completos.append(f"atividade_{i}")

    # Agora vem os campos do supervisor
    nomes_completos += ["nome_supervisor", "formacao_supervisor", "registro_conselho"]

    # Lista de índices obrigatórios
    indices_obrigatorios = [
        0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11,           # empresa
        12, 13, 14, 15, 16, 17, 18, 19, 20,          # estudante
        22, 23, 24, 25, 26,                          # estudante continuação
        27, 28, 29,                                  # acadêmicos
        30, 31, 32,                                  # datas
        33, 34, 35,                                  # horários
        36, 37,                                      # seguradora, apólice
        38, 39, 40, 41,                              # remuneração
        42, 44,                                      # auxilio e contraprestação
        46, 47, 48, 49,                              # plano de atividades
        61, 62                                       # nome_supervisor, formacao_supervisor
    ]

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
        "formacao_supervisor": "Formação do(a) Supervisor(a)"
    }

#     "valor_bolsa": "Valor da Bolsa",
#         "valor_extenso": "Valor por Extenso",

    # Desempacotamento
    (
        tipo_estagio, razao_social, cnpj, nome_fantasia, endereco, bairro,
        cep, complemento, cidade, uf, email, telefone,
        representante, cpf_repr, nome_estudante, nascimento, cpf_estudante, rg,
        endereco_estudante, bairro_estudante, cep_estudante, complemento_estudante,
        cidade_estudante, uf_estudante, email_estudante, telefone_estudante, curso_estudante,
        ano_periodo, matricula, orientador, data_inicio, data_termino, total_dias,
        horas_diarias, horas_semana_estagio, total_horas_estagio,
        seguradora, apolice,
        modalidade_estagio, remunerado, valor_bolsa, valor_extenso,
        auxilio_transporte, especificacao_auxilio,
        contraprestacao, especificacao_contraprestacao,
        horas_diarias_plano, horas_semanais_plano, total_horas_plano,
        horario_atividades,
        atividade_1, atividade_2, atividade_3, atividade_4, atividade_5,
        atividade_6, atividade_7, atividade_8, atividade_9, atividade_10,
        nome_supervisor, formacao_supervisor, registro_conselho
    ) = args

    if remunerado == "Sim":
        if not str(valor_bolsa).strip():
            gr.Warning("⚠️ O campo 'Valor da Bolsa' é obrigatório para a opção Sim.")
            return [gr.update() for _ in args]

        if not str(valor_extenso).strip():
            gr.Warning("⚠️ O campo 'Valor por Extenso' é obrigatório para a opção Sim.")
            return [gr.update() for _ in args]

    # 5. Validação condicional de campos dependentes
    if auxilio_transporte == "Sim":
        if not str(especificacao_auxilio).strip():
            gr.Warning("⚠️ O campo 'Especificação do Auxílio Transporte' é obrigatório para a opção Sim.")
            return [gr.update() for _ in args]

    if contraprestacao == "Sim":
        if not str(especificacao_contraprestacao).strip():
            gr.Warning("⚠️ O campo 'Especificação da Contraprestação' é obrigatório para a opção Sim.")
            return [gr.update() for _ in args]


    # Validação de obrigatórios
    for nome in campos_obrigatorios:
        try:
            i = nomes_completos.index(nome)
            valor = args[i]
            if valor is None or str(valor).strip().lower() in ["", "none"]:
                gr.Warning(f"⚠️ O campo '{campos_obrigatorios[nome]}' é obrigatório.")
                return [gr.update() for _ in args]
        except ValueError:
            print(f"[ERRO] Campo '{nome}' não está em nomes_completos.")
            continue

    # Datas
    if not data_inicio or not data_termino:
        gr.Warning("Você precisa informar a data de início e término do estágio.")
        return [gr.update() for _ in args]

    if not nascimento:
        gr.Warning(f"⚠️ O campo 'Data de Nascimento' é obrigatório")
        return [gr.update() for _ in args]

    try:
        dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_termino = datetime.strptime(data_termino, "%Y-%m-%d")
        dt_nascimento = datetime.strptime(nascimento, "%Y-%m-%d")
    except ValueError:
        gr.Warning("Formato inválido de data. Use o seletor de calendário.")
        return [gr.update() for _ in args]

    if dt_termino < dt_inicio:
        gr.Warning("A data de término não pode ser anterior à data de início.")
        return [gr.update() for _ in args]

    data_inicio = dt_inicio.strftime("%d/%m/%Y")
    data_termino = dt_termino.strftime("%d/%m/%Y")
    nascimento = dt_nascimento.strftime("%d/%m/%Y")

#     atividades = [
#         atividade_1, atividade_2, atividade_3, atividade_4, atividade_5,
#         atividade_6, atividade_7, atividade_8, atividade_9, atividade_10
#     ]

#     if not any(a.strip() for a in atividades if isinstance(a, str)):
#         gr.Warning("⚠️ Pelo menos uma atividade deve ser preenchida.")
#         return [gr.update() for _ in args]


    print("=== TERMO DE COMPROMISSO DE ESTÁGIO ===")
    print(f"Tipo de Estágio: {tipo_estagio}")
    print(f"Razão Social: {razao_social}")
    print(f"CNPJ: {cnpj}")
    print(f"Nome Fantasia: {nome_fantasia}")
    print(f"Endereço: {endereco}")
    print(f"Bairro: {bairro}")
    print(f"CEP: {cep}")
    print(f"Complemento: {complemento}")
    print(f"Cidade: {cidade}")
    print(f"UF: {uf}")
    print(f"E-mail: {email}")
    print(f"Telefone: {telefone}")
    print(f"Representante: {representante}")
    print(f"CPF Representante: {cpf_repr}")
    print(f"Nome do(a) Estudante: {nome_estudante}")
    print(f"Nascimento: {nascimento}")
    print(f"CPF do(a) Estudante: {cpf_estudante}")
    print(f"RG do(a) Estudante: {rg}")
    print(f"Complemento do(a) Estudante: {complemento_estudante}")
    print(f"Cidade do(a) Estudante: {cidade_estudante}")
    print(f"UF do(a) Estudante: {uf_estudante}")
    print(f"E-mail do(a) Estudante: {email_estudante}")
    print(f"Telefone do(a) Estudante: {telefone_estudante}")
    print(f"Curso do(a) Estudante: {curso_estudante}")
    print(f"Ano/Período Letivo: {ano_periodo}")
    print(f"Matrícula: {matricula}")
    print(f"Orientador(a): {orientador}")
    print(f"Data de Início: {data_inicio}")
    print(f"Data de Término: {data_termino}")
    print(f"Total de Dias de Estágio: {total_dias}")
    print(f"Horas Diárias: {horas_diarias}")
    print(f"Horas Semanais de Estágio: {horas_semana_estagio}")
    print(f"Total de Horas de Estágio: {total_horas_estagio}")
    print(f"Seguradora: {seguradora}")
    print(f"Apólice: {apolice}")
    print(f"Modalidade do Estágio: {modalidade_estagio}")
    print(f"Remunerado: {remunerado}")
    print(f"Valor da Bolsa: {valor_bolsa}")
    print(f"Valor por Extenso: {valor_extenso}")
    print(f"Auxílio Transporte: {auxilio_transporte}")
    print(f"Especificação do Auxílio Transporte: {especificacao_auxilio}")
    print(f"Contraprestação de Serviços: {contraprestacao}")
    print(f"Especificação da Contraprestação: {especificacao_contraprestacao}")
    print(f"Horas Diárias no Plano: {horas_diarias_plano}")
    print(f"Horas Semanais do Plano de Atividades: {horas_semanais_plano}")
    print(f"Total de Horas do Plano de Atividades: {total_horas_plano}")
    print(f"Horário das Atividades: {horario_atividades}")

    print("=== ATIVIDADES ===")
    for i, atividade in enumerate([
        atividade_1, atividade_2, atividade_3, atividade_4, atividade_5,
        atividade_6, atividade_7, atividade_8, atividade_9, atividade_10
    ], start=1):
        valor = str(atividade).strip()
        if valor:
            print(f"Atividade {i}: {valor}")

    print("=== SUPERVISOR(A) DO ESTÁGIO ===")
    print(f"Nome do(a) Supervisor(a): {nome_supervisor}")
    print(f"Formação do(a) Supervisor(a): {formacao_supervisor}")
    print(f"Registro no Conselho: {registro_conselho}")

    print("✅ Termo registrado com sucesso!")
    gr.Info("✅ Termo registrado com sucesso!")


    # Limpa os campos após submissão (se desejar)
    return [None] * len(args)


with gr.Blocks(theme="default") as demo:

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

    with gr.Row():
        razao_social = gr.Text(label="Razão Social*")
        cnpj = gr.Text(label="CNPJ (00.000.000/0000-00)*", placeholder="Ex: 12.345.678/0001-99")

    nome_fantasia = gr.Text(label="Nome Fantasia*")

    with gr.Row():
        endereco = gr.Text(label="Endereço*")
        bairro = gr.Text(label="Bairro*")
        cep = gr.Text(label="CEP (00000-000)*", placeholder="Ex: 12345-000")

    with gr.Row():
        complemento = gr.Text(label="Complemento")
        cidade = gr.Text(label="Cidade*")
        uf = gr.Dropdown(
            label="UF*",
            choices=[
                "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
                "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
                "RO", "RR", "RS", "SC", "SE", "SP", "TO"
            ],
            value=None,
            type="value",        # retorna o texto selecionado
            interactive=True     # garante que está habilitado para o usuário
        )

    with gr.Row():
        email = gr.Text(label="E-mail*")
        telefone = gr.Text(label="Telefone (00) 00000-0000*", placeholder="Ex: (64) 91234-5678")

    with gr.Row():
        representante = gr.Text(label="Representante legal*")
        cpf_repr = gr.Text(label="CPF (000.000.000-00)*", placeholder="Ex: 123.456.789-00")

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

        cpf_estudante = gr.Text(label="CPF (000.000.000-00)*", placeholder="Ex: 123.456.789-00")
        rg = gr.Text(label="RG*")

    with gr.Row():
        endereco_estudante = gr.Text(label="Endereço*")
        bairro_estudante = gr.Text(label="Bairro*")
        cep_estudante = gr.Text(label="CEP (00000-000)*", placeholder="Ex: 12345-000")

    with gr.Row():
        complemento_estudante = gr.Text(label="Complemento")
        cidade_estudante = gr.Text(label="Cidade*")
        uf_estudante = gr.Dropdown(
            label="UF*",
            choices=[
                "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
                "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
                "RO", "RR", "RS", "SC", "SE", "SP", "TO"
            ],
            value=None,
            type="value",        # retorna o texto selecionado
            interactive=True     # garante que está habilitado para o usuário
        )

    with gr.Row():
        email_estudante = gr.Text(label="E-mail*")
        telefone_estudante = gr.Text(label="Telefone (00) 00000-0000)*", placeholder="Ex: (64) 91234-5678")

    curso_estudante = gr.Dropdown(
    label="Curso*",
    choices=[
        "Bacharelado em Administração",
        "Bacharelado em Zootecnia",
        "Técnico em Agropecuária",
        "Técnico em Administração",
        "Técnico em Informática"
    ],
    value=None
    )

    with gr.Row():
        ano_periodo = gr.Text(label="Ano/Período do Curso*", placeholder="Ex: 8º")
        matricula = gr.Text(label="Número de Matrícula*")

    orientador = gr.Text(label="Professor(a) orientador(a)*")

    gr.Markdown("""
ambos com a interveniência do **INSTITUTO FEDERAL GOIANO - CAMPUS CAMPOS BELOS**, situado à Rodovia GO118, Km 341, Setor Novo Horizonte, em Campos Belos – GO, CEP.73.840.000, inscrito no CNPJ de n.º 10.651.417/0012-20, neste ato representado pelo Diretor-Geral, **Prof. Althiéris de Souza Saraiva** (**Portaria N.º 1.653 REI/IFGOIANO, de 14/03/2024, D.O.U de 15/03/2024**) e pelo coordenador de Extensão, **Prof.º João Rufino Junior** (**Portaria N.º 1.086, D.O.U. de 06/12/2018**), celebram entre si este termo, convencionado às cláusulas e condições seguintes:

### CLÁUSULA PRIMEIRA – DO OBJETO
Este **TERMO** tem por objeto formalizar as condições para a realização de **ESTÁGIOS** de Estudantes, como forma de complementação do processo de ensino – aprendizagem, nos termos e condições da Lei 11.788/08 e pelas normas de estágio do Instituto Federal Goiano.

### CLÁUSULA SEGUNDA – DA DURAÇÃO
Este **TERMO** terá vigência conforme descrito na tabela abaixo, podendo ser rescindido unilateralmente por qualquer das partes, a qualquer momento, sem ônus, multas, mediante comunicação feita por escrito, com, no mínimo, cinco dias de antecedência:
""")

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
            placeholder="Ex: 30h"
        )
        total_horas_estagio = gr.Text(
            label="Total de horas do estágio*",
            placeholder="Ex: 240 horas"
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

    horas_diarias_plano = gr.Radio(
        label="Horas diárias (marque o valor correspondente)*", 
        choices=[str(i) for i in range(1, 9)], 
        type="value"
    )

    with gr.Row():
        horas_semanais_plano = gr.Text(label="Horas semanais*", placeholder="Ex: 30h")
        total_horas_plano = gr.Text(label="Total de horas do estágio*", placeholder="Ex: 300 horas")
        horario_atividades = gr.Text(label="Horário de realização das atividades*", placeholder="Ex: 13h às 17h30min")

    gr.Markdown("**As seguintes atividades serão desenvolvidas:**")

    atividades = []
    for i in range(1, 11):
        atividades.append(gr.Text(label=f"Atividade {i}", placeholder=f"Descreva a atividade {i}"))

    gr.Markdown("""
    **O(A) concedente designará para supervisor(a) do Estágio:**  
    """)

    nome_supervisor = gr.Text(label="Nome do(a) Supervisor(a)*", placeholder="Ex: José da Silva")
    formacao_supervisor = gr.Text(label="Formação do(a) Supervisor(a)*", placeholder="Ex: Advogado")
    registro_conselho = gr.Text(label="Nº do registro no conselho (quando este o exigir)", placeholder="Ex: OAB-TO: 0.000")

    gr.Markdown("""
        ### CLÁUSULA DÉCIMA – DO FORO
        O Foro para dirimir as questões oriundas deste instrumento é o da Justiça Federal, Subseção Judiciária de Goiânia – Estado de Goiás, conforme determina o Art. 109, I, da Constituição Federal.

        """)


    # Botão de submissão
    botao = gr.Button("Registrar Termo")
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
            nome_supervisor, formacao_supervisor, registro_conselho
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
            nome_supervisor, formacao_supervisor, registro_conselho
        ]
    )




# In[ ]:





import os
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.queue().launch(server_name="0.0.0.0", server_port=port)
