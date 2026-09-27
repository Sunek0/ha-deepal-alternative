# Guia completo: conta secundária e instalação do Deepal Alternative

Guia passo a passo para ligar o teu carro Changan/Deepal ao Home Assistant com a integração
**Deepal Alternative**. Cobre o processo completo: desde a criação da conta secundária na app My
Changan até à instalação da integração com o HACS e à sua configuração.

## Índice

1. [Porquê usar uma conta secundária](#porquê-usar-uma-conta-secundária)
2. [Requisitos prévios](#requisitos-prévios)
3. [Parte 1: conta secundária na My Changan](#parte-1-conta-secundária-na-my-changan)
4. [Parte 2: instalação da integração](#parte-2-instalação-da-integração)
5. [Notas e resolução de problemas](#notas-e-resolução-de-problemas)

## Porquê usar uma conta secundária

A integração inicia sessão na plataforma oficial da My Changan. Uma mesma conta não pode manter duas
sessões ativas ao mesmo tempo: se o Home Assistant entrar com a tua conta principal, é possível que
a app do telemóvel termine a sessão e, se voltares a entrar na app, a sessão do Home Assistant é
invalidada.

A solução recomendada é criar uma **conta secundária**, partilhar o carro a partir da conta
principal e usar apenas a secundária no Home Assistant. Assim a tua conta principal continua a
funcionar normalmente no telemóvel.

## Requisitos prévios

- Um veículo Deepal compatível (S05, S07) associado a uma conta My Changan.
- Acesso à app **My Changan** com a conta principal.
- Um email ou número de telemóvel diferente para a conta secundária.
- Home Assistant 2026.3.0 ou superior.
- [HACS](https://hacs.xyz/docs/use/download/download/) instalado. Se ainda não o tens, segue as
  instruções oficiais de instalação em <https://hacs.xyz/docs/use/download/download/>.

## Parte 1: conta secundária na My Changan

### 1. Criar a conta secundária

1. Abre a app **My Changan** e cria uma conta nova com um email ou um número de telemóvel diferente
   do da tua conta principal.
2. Anota as credenciais (email/telemóvel e código de acesso): serão as que vais usar no Home
   Assistant.

### 2. Partilhar o veículo a partir da conta principal

1. Termina a sessão da conta secundária e inicia sessão na app com a **conta principal**.
2. Toca no botão **partilhar** do ecrã principal.
3. Convida a conta secundária que acabaste de criar, indicando um período de validade permanente.

### 3. Aceitar o acesso e criar a palavra-passe de controlo

1. Termina a sessão da **conta principal** na app e inicia sessão com a **conta secundária**.
2. Aceita o acesso ao carro partilhado.
3. Vai ao **centro pessoal** (perfil) e toca em **O meu veículo**.
4. Seleciona o carro partilhado.
5. Toca em **Palavra-passe de controlo do veículo** e cria uma palavra-passe (PIN). Anota-a: é o PIN
   que o Home Assistant vai pedir para os comandos de portas, janelas e bagageira.

> Se não encontrares essa opção na tua versão da app, tenta baixar as janelas pela app: vai pedir-te
> para criar o PIN de controlo. Cria-o e confirma que o comando funciona.

### 4. Voltar à conta principal

1. Termina a sessão da conta secundária e volta a iniciar sessão com a **conta principal** no
   telemóvel.
2. A conta principal fica como proprietária do veículo; a secundária usa-se apenas no Home
   Assistant.

## Parte 2: instalação da integração

### 5. Instalar o HACS (se ainda não o tens)

O HACS é o gestor de integrações personalizadas do Home Assistant. Se ainda não o tens instalado,
segue o guia oficial: <https://hacs.xyz/docs/use/download/download/>. Depois de instalado, aparece o
separador **HACS** na barra lateral do Home Assistant.

### 6. Adicionar o repositório ao HACS

1. No Home Assistant, entra no separador **HACS**.
2. Abre o menu de três pontos (⋮) no canto superior direito e escolhe **Repositórios
   personalizados**.
3. Cola o URL do repositório:
   `https://github.com/Sunek0/ha-deepal-alternative`
4. Em **Categoria**, seleciona **Integração** e toca em **Adicionar**.

### 7. Instalar o Deepal Alternative e reiniciar

1. No HACS, procura **Deepal Alternative** (podes usar a pesquisa do separador ou a categoria
   **Integrações**).
2. Abre a ficha e toca em **Transferir**.
3. **Reinicia o Home Assistant** para carregar a nova integração.

### 8. Adicionar a integração

1. Vai a **Definições → Dispositivos e serviços**.
2. Toca em **Adicionar integração** e procura **Deepal Alternative**.
3. Em **Plataforma**, escolhe **International (Europe)** (a opção SDA (China) é apenas para contas
   da China continental com access token).
4. Em **Método de início de sessão**, escolhe como a tua conta secundária inicia sessão:
   - **Email code**: é enviado um código de verificação para o email.
   - **Phone/SMS code**: é enviado um código de verificação por SMS para o telemóvel.
5. Preenche os campos do formulário:
   - **País de venda**: o país registado na tua conta My Changan (por exemplo, Espanha).
   - **Email** ou **Número de telemóvel** (sem indicativo) da conta **secundária**.
6. Espera pelo código de verificação (email ou SMS) e introduz-o em **Código de verificação**.
7. A integração valida a conta e cria um dispositivo por veículo. Pronto.

### 9. Guardar o PIN de controlo remoto

Este passo **só é necessário** para poderes usar os comandos assinados (trancar portas, janelas e
bagageira) e para que o Home Assistant crie as respetivas entidades:

1. Vai a **Definições → Dispositivos e serviços → Deepal Alternative**.
2. Toca em **Configurar**.
3. Em **PIN de controlo remoto**, introduz a palavra-passe que criaste no passo 3 com a conta
   secundária.
4. Guarda. As entidades das portas, janelas e bagageira aparecem no dispositivo do carro.

### 10. Confirmar que funciona

- Abre a página do dispositivo do veículo: deves ver os sensores de bateria, autonomia, carregamento
  e as restantes telemetrias.
- Testa um comando seguro (por exemplo, acender as luzes ou o clima) e confirma que o carro
  responde.
- Os comandos que dependem do PIN (portas, janelas, bagageira) são assinados com o PIN criado com a
  conta secundária; se falharem, revê o passo 9.

## Notas e resolução de problemas

- **Não consigo controlar nada**: verifica primeiro se a app oficial consegue fazê-lo com a mesma
  conta. O carro às vezes recusa os comandos remotos até ter sido conduzido durante uns minutos.
- **"Remote control PIN is not set" mesmo depois de já ter guardado o PIN**: o PIN não foi criado
  com a conta que o Home Assistant usa. Inicia sessão na app com a conta secundária, cria o PIN
  (passo 3) e volta a guardá-lo nas opções da integração.
- **O Home Assistant pede para reautenticar**: a sessão foi invalidada pela app ou por outro
  dispositivo. Volta a iniciar sessão; com a conta secundária é muito menos frequente.
- **Os valores parecem antigos**: o carro só comunica telemetria quando está desperto; a integração
  mostra a última leitura conhecida até voltar a comunicar.
- **Aviso**: projeto não oficial, sem relação com a Changan Automobile. Os comandos remotos atuam
  sobre o carro real: certifica-te de que é seguro antes de usar trancas, janelas, bagageira, clima,
  luzes ou buzina.
