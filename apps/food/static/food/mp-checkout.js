/**
 * Mercado Pago Checkout Transparente — Food Hub.
 * Tokeniza no browser; backend recebe apenas token.
 */
(function () {
  var cfg = window.FOOD_MP_CONFIG || {};
  var form = document.getElementById("food-card-form");
  if (!form) return;

  form.addEventListener("submit", function (event) {
    var tokenInput = document.getElementById("food-card-token");
    var methodInput = document.getElementById("food-card-payment-method-id");
    var issuerInput = document.getElementById("food-card-issuer-id");

    if (cfg.stub) {
      if (tokenInput) tokenInput.value = "stub_card_token";
      if (methodInput) methodInput.value = "visa";
      if (issuerInput) issuerInput.value = "";
      return true;
    }

    if (!cfg.publicKey || typeof MercadoPago === "undefined") {
      event.preventDefault();
      alert("Mercado Pago SDK não carregado. Configure a public_key do tenant.");
      return false;
    }

    event.preventDefault();
    var mp = new MercadoPago(cfg.publicKey, { locale: "pt-BR" });
    var docType = document.getElementById("food-card-doc-type");
    var docNumber = document.getElementById("food-card-doc-number");
    var cardNumber = document.getElementById("food-card-number");
    var cardName = document.getElementById("food-card-name");
    var expMonth = document.getElementById("food-card-exp-month");
    var expYear = document.getElementById("food-card-exp-year");
    var cvv = document.getElementById("food-card-cvv");

    mp.createCardToken({
      cardNumber: cardNumber ? cardNumber.value : "",
      cardholderName: cardName ? cardName.value : "",
      cardExpirationMonth: expMonth ? expMonth.value : "",
      cardExpirationYear: expYear ? expYear.value : "",
      securityCode: cvv ? cvv.value : "",
      identificationType: docType ? docType.value : "CPF",
      identificationNumber: docNumber ? docNumber.value : "",
    })
      .then(function (result) {
        if (!result || !result.id) {
          throw new Error("Token não gerado");
        }
        if (tokenInput) tokenInput.value = result.id;
        if (methodInput) {
          methodInput.value = result.payment_method_id || "visa";
        }
        if (issuerInput) {
          issuerInput.value = result.issuer_id || "";
        }
        if (cardNumber) cardNumber.value = "";
        if (cvv) cvv.value = "";
        form.submit();
      })
      .catch(function (err) {
        alert("Falha ao tokenizar cartão: " + (err.message || err));
      });

    return false;
  });
})();
