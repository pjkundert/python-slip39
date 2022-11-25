contract MultiSend {
    function MultiSend(address[] recipients, uint[] amounts, address remainder) {
        if(recipients.length != amounts.length)
            throw;

        for(uint i = 0; i < recipients.length; i++) {
            recipients[i].send(amounts[i]);
        }

        selfdestruct(remainder);
    }
}
